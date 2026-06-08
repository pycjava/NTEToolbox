def strip_jsonc_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    quote = ""
    escaped = False
    index = 0

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                in_string = False
            index += 1
            continue

        if char in ('"', "'"):
            in_string = True
            quote = char
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            while index < len(text) and text[index] != "\n":
                index += 1
            if index < len(text):
                result.append("\n")
                index += 1
            continue

        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and not (
                text[index] == "*" and text[index + 1] == "/"
            ):
                index += 1
            index += 2
            continue

        result.append(char)
        index += 1

    return "".join(result)
