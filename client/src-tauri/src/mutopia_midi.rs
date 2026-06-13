use serde::{Deserialize, Serialize};
use std::{
    collections::HashSet,
    fs,
    path::PathBuf,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::AppHandle;

const MUTOPIA_PIANO_LISTING_URL: &str =
    "https://www.mutopiaproject.org/cgibin/make-table.cgi?Instrument=Piano";
const MUTOPIA_ORIGIN: &str = "https://www.mutopiaproject.org";
const MAX_PUBLIC_DOMAIN_RESULTS: usize = 80;
const MAX_MUTOPIA_LISTING_PAGES: usize = 20;
const MAX_MIDI_BYTES: usize = 8 * 1024 * 1024;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MutopiaMidiEntry {
    pub id: String,
    pub title: String,
    pub composer: String,
    pub instrument: String,
    pub style: String,
    pub license: String,
    pub midi_url: String,
    pub source_url: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MutopiaMidiDownloadRequest {
    pub title: String,
    pub composer: String,
    pub license: String,
    pub midi_url: String,
}

pub fn list_public_domain_piano_midi() -> Result<Vec<MutopiaMidiEntry>, String> {
    let mut entries = Vec::new();
    let mut seen_midi_urls = HashSet::new();

    for page_index in 0..MAX_MUTOPIA_LISTING_PAGES {
        let start_at = page_index * 10;
        let html = fetch_text(&listing_url(start_at))?;
        let page_entries = parse_public_domain_midi_listing(&html);

        for entry in page_entries {
            if seen_midi_urls.insert(entry.midi_url.clone()) {
                entries.push(entry);
            }
            if entries.len() >= MAX_PUBLIC_DOMAIN_RESULTS {
                return Ok(entries);
            }
        }

        if !html.contains("Next 10") {
            break;
        }
    }

    Ok(entries)
}

/// Returns the fixed MIDI directory next to the running executable.
fn resolve_midi_dir() -> Result<PathBuf, String> {
    let exe_dir = std::env::current_exe()
        .map_err(|error| format!("Failed to get executable path: {error}"))?
        .parent()
        .ok_or("Failed to resolve executable directory")?
        .to_path_buf();
    Ok(exe_dir.join("midi"))
}

pub fn download_midi(
    _app: &AppHandle,
    request: &MutopiaMidiDownloadRequest,
) -> Result<String, String> {
    validate_download_request(request)?;

    let midi_dir = resolve_midi_dir()?;
    fs::create_dir_all(&midi_dir)
        .map_err(|error| format!("Failed to create MIDI directory: {error}"))?;

    let file_path = available_path(
        &midi_dir,
        &safe_file_stem(&format!("{} {}", request.composer, request.title)),
        "mid",
    );
    download_file(&request.midi_url, &file_path)?;

    Ok(file_path.to_string_lossy().to_string())
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DownloadedMidiEntry {
    pub file_name: String,
    pub display_name: String,
    pub file_path: String,
}

pub fn list_downloaded_midi() -> Result<Vec<DownloadedMidiEntry>, String> {
    let midi_dir = resolve_midi_dir()?;

    if !midi_dir.exists() {
        return Ok(vec![]);
    }

    let mut entries = Vec::new();
    let dir_entries = fs::read_dir(&midi_dir)
        .map_err(|error| format!("Failed to read MIDI directory: {error}"))?;

    for entry in dir_entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("mid") {
            continue;
        }
        let file_name = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();
        let display_name = file_name.replace('-', " ");
        let file_path = path.to_string_lossy().to_string();
        entries.push(DownloadedMidiEntry {
            file_name,
            display_name,
            file_path,
        });
    }

    entries.sort_by(|a, b| a.display_name.cmp(&b.display_name));
    Ok(entries)
}

pub fn parse_public_domain_midi_listing(html: &str) -> Vec<MutopiaMidiEntry> {
    let mut entries = Vec::new();
    let mut seen_midi_urls = HashSet::new();
    let mut rest = html;

    while let Some(start_index) = rest.find("<table class=\"table-bordered result-table\">") {
        rest = &rest[start_index..];
        let Some(end_index) = rest.find("</table>") else {
            break;
        };
        let table = &rest[..end_index + "</table>".len()];
        rest = &rest[end_index + "</table>".len()..];

        if !table.contains("legal.html#publicdomain") {
            continue;
        }

        let rows = extract_rows(table);
        if rows.len() < 4 {
            continue;
        }

        let first_row = extract_cells(&rows[0]);
        let second_row = extract_cells(&rows[1]);
        let third_row = extract_cells(&rows[2]);
        if first_row.len() < 2 || second_row.len() < 3 || third_row.len() < 3 {
            continue;
        }

        let title = clean_html_text(&first_row[0]);
        let composer = clean_composer(&clean_html_text(&first_row[1]));
        let instrument = clean_instrument(&clean_html_text(&second_row[0]));
        let style = clean_html_text(&second_row[2]);
        let license = clean_html_text(&third_row[1]);
        if title.is_empty() || license != "Public Domain" {
            continue;
        }

        let Some(midi_url) = extract_mid_url(table) else {
            continue;
        };
        if !seen_midi_urls.insert(midi_url.clone()) {
            continue;
        }

        let source_url = extract_piece_info_url(&third_row[2]);
        entries.push(MutopiaMidiEntry {
            id: entry_id(&title, &composer, &midi_url),
            title,
            composer,
            instrument,
            style,
            license,
            midi_url,
            source_url,
        });

        if entries.len() >= MAX_PUBLIC_DOMAIN_RESULTS {
            break;
        }
    }

    entries
}

pub fn validate_download_request(request: &MutopiaMidiDownloadRequest) -> Result<(), String> {
    if request.license != "Public Domain" {
        return Err("Only Mutopia Public Domain MIDI files can be downloaded here".to_string());
    }

    if !request.midi_url.starts_with(&format!("{MUTOPIA_ORIGIN}/ftp/")) {
        return Err("MIDI URL must be under mutopiaproject.org/ftp".to_string());
    }

    if !request.midi_url.to_ascii_lowercase().ends_with(".mid") {
        return Err("MIDI URL must point to a .mid file".to_string());
    }

    Ok(())
}

fn extract_rows(table: &str) -> Vec<String> {
    let mut rows = Vec::new();
    let mut rest = table;
    while let Some(start_index) = rest.find("<tr>") {
        rest = &rest[start_index + "<tr>".len()..];
        let Some(end_index) = rest.find("</tr>") else {
            break;
        };
        rows.push(rest[..end_index].to_string());
        rest = &rest[end_index + "</tr>".len()..];
    }
    rows
}

fn extract_cells(row: &str) -> Vec<String> {
    let mut cells = Vec::new();
    let mut rest = row;
    while let Some(start_index) = rest.find("<td") {
        rest = &rest[start_index..];
        let Some(close_index) = rest.find('>') else {
            break;
        };
        rest = &rest[close_index + 1..];
        let Some(end_index) = rest.find("</td>") else {
            break;
        };
        cells.push(rest[..end_index].to_string());
        rest = &rest[end_index + "</td>".len()..];
    }
    cells
}

fn extract_mid_url(table: &str) -> Option<String> {
    extract_href_by_label(table, ".mid file")
        .filter(|url| url.starts_with(MUTOPIA_ORIGIN) && url.to_ascii_lowercase().ends_with(".mid"))
}

fn extract_piece_info_url(cell: &str) -> String {
    extract_href_by_label(cell, "More Information")
        .map(|url| {
            if url.starts_with("http") {
                url
            } else {
                format!("{MUTOPIA_ORIGIN}/cgibin/{}", url.trim_start_matches("./"))
            }
        })
        .unwrap_or_else(|| MUTOPIA_PIANO_LISTING_URL.to_string())
}

fn extract_href_by_label(fragment: &str, label: &str) -> Option<String> {
    let mut rest = fragment;
    while let Some(anchor_index) = rest.find("<a ") {
        rest = &rest[anchor_index..];
        let Some(anchor_end) = rest.find("</a>") else {
            break;
        };
        let anchor = &rest[..anchor_end + "</a>".len()];
        rest = &rest[anchor_end + "</a>".len()..];

        if !clean_html_text(anchor).contains(label) {
            continue;
        }

        let Some(href_index) = anchor.find("href=\"") else {
            continue;
        };
        let href_start = href_index + "href=\"".len();
        let Some(href_end) = anchor[href_start..].find('"') else {
            continue;
        };
        return Some(decode_html_entities(&anchor[href_start..href_start + href_end]));
    }
    None
}

fn clean_html_text(value: &str) -> String {
    let mut output = String::new();
    let mut in_tag = false;
    for char in value.chars() {
        match char {
            '<' => in_tag = true,
            '>' => {
                in_tag = false;
                output.push(' ');
            }
            _ if !in_tag => output.push(char),
            _ => {}
        }
    }
    decode_html_entities(&output)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn decode_html_entities(value: &str) -> String {
    value
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
}

fn clean_composer(value: &str) -> String {
    value
        .strip_prefix("by ")
        .unwrap_or(value)
        .split(" (")
        .next()
        .unwrap_or(value)
        .trim()
        .to_string()
}

fn clean_instrument(value: &str) -> String {
    value
        .strip_prefix("for ")
        .unwrap_or(value)
        .trim()
        .to_string()
}

fn entry_id(title: &str, composer: &str, midi_url: &str) -> String {
    let base = format!("{composer}-{title}");
    let mut id = safe_file_stem(&base);
    if id == "midi" {
        id = safe_file_stem(midi_url);
    }
    id
}

fn safe_file_stem(value: &str) -> String {
    let mut output = String::new();
    let mut previous_dash = false;

    for char in value.chars().flat_map(char::to_lowercase) {
        if char.is_ascii_alphanumeric() {
            output.push(char);
            previous_dash = false;
        } else if !previous_dash && !output.is_empty() {
            output.push('-');
            previous_dash = true;
        }
    }

    let trimmed = output.trim_matches('-').to_string();
    if trimmed.is_empty() {
        "midi".to_string()
    } else {
        trimmed
    }
}

fn available_path(directory: &std::path::Path, stem: &str, extension: &str) -> PathBuf {
    let first = directory.join(format!("{stem}.{extension}"));
    if !first.exists() {
        return first;
    }

    for index in 1.. {
        let candidate = directory.join(format!("{stem}-{index}.{extension}"));
        if !candidate.exists() {
            return candidate;
        }
    }

    unreachable!()
}

fn listing_url(start_at: usize) -> String {
    if start_at == 0 {
        return MUTOPIA_PIANO_LISTING_URL.to_string();
    }

    format!(
        "{MUTOPIA_ORIGIN}/cgibin/make-table.cgi?startat={start_at}&searchingfor=&Composer=&Instrument=Piano&Style=&collection=&id=&solo=&recent=&timelength=&timeunit=&lilyversion=&preview="
    )
}

fn fetch_text(url: &str) -> Result<String, String> {
    let temp_path = std::env::temp_dir().join(format!(
        "ntetoolbox-mutopia-{}-{}.html",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_millis())
            .unwrap_or_default()
    ));

    let result = (|| {
        powershell_web_request(url, Some(&temp_path))?;
        let bytes = fs::read(&temp_path)
            .map_err(|error| format!("Failed to read Mutopia listing: {error}"))?;
        Ok(String::from_utf8_lossy(&bytes).to_string())
    })();

    let _ = fs::remove_file(&temp_path);
    result
}

fn download_file(url: &str, output_path: &std::path::Path) -> Result<(), String> {
    powershell_web_request(url, Some(output_path))?;

    let metadata = fs::metadata(output_path)
        .map_err(|error| format!("Failed to verify downloaded MIDI file: {error}"))?;
    if metadata.len() as usize > MAX_MIDI_BYTES {
        let _ = fs::remove_file(output_path);
        return Err("Downloaded MIDI is too large".to_string());
    }
    Ok(())
}

fn powershell_web_request(url: &str, output_path: Option<&std::path::Path>) -> Result<Vec<u8>, String> {
    let ps_script = match output_path {
        Some(path) => format!(
            "$ProgressPreference='SilentlyContinue'; \
             Invoke-WebRequest -UseBasicParsing -Uri '{}' -OutFile '{}'",
            url.replace("'", "''"),
            path.to_string_lossy().replace("'", "''"),
        ),
        None => format!(
            "$ProgressPreference='SilentlyContinue'; \
             [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; \
             (Invoke-WebRequest -UseBasicParsing -Uri '{}').Content",
            url.replace("'", "''"),
        ),
    };

    let mut command = Command::new("powershell");
    command.args([
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        &ps_script,
    ]);

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let output = command
        .output()
        .map_err(|error| format!("Failed to run PowerShell download helper: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "Mutopia download helper failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }

    Ok(output.stdout)
}
