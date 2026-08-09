import interfaceJsonc from "../../assets/interface.jsonc?raw";

import type {
  GameDefinition,
  InputOptionDefinition,
  OptionDefinition,
  OptionInputDefinition,
  OptionValue,
  PipelineOverride
} from "./clientModel";

type MaaInterfaceConfig = {
  name?: string;
  description?: string;
  controller?: MaaControllerDefinition[];
  task?: MaaTaskDefinition[];
  option?: Record<string, MaaOptionDefinition>;
};

type MaaControllerDefinition = {
  name: string;
  type?: string;
};

type MaaTaskDefinition = {
  name: string;
  entry?: string;
  option?: string[];
};

type MaaOptionDefinition = {
  type: "switch" | "select" | "input";
  label?: string;
  description?: string;
  inputs?: MaaInputDefinition[];
  cases?: MaaCaseDefinition[];
  default_case?: string;
  pipeline_override?: PipelineOverride;
};

type MaaCaseDefinition = {
  name: string;
  label?: string;
  description?: string;
  option?: string[];
  pipeline_override?: PipelineOverride;
};

type MaaInputDefinition = {
  name: string;
  label?: string;
  description?: string;
  pipeline_type?: "int" | "string" | "bool";
  default?: string;
};

export type ClientData = {
  globalSettingsOption: InputOptionDefinition;
  globalSettingsDefaultValues: Record<string, OptionValue>;
  nteOptions: Record<string, OptionDefinition>;
  initialGames: GameDefinition[];
};

const GLOBAL_SETTINGS_TASK_NAME = "全局设置";
const DEFAULT_GAME_ID = "nte";
const DEFAULT_GAME_SHORT_NAME = "异";
const DEFAULT_GAME_ICON = "/nte-icon.png";
const HS_GAME_ID = "hs";

/** 炉石传说：独立后端进程（hscoachd）驱动，不走 MaaPiCli 任务系统。 */
const HS_GAME: GameDefinition = {
  id: HS_GAME_ID,
  name: "炉石传说",
  description: "AI 教练：实时对局解析与出牌建议",
  shortName: "炉",
  status: "ready",
  kind: "process",
  features: [],
  controller: {
    controllerType: "",
    controllerTypes: [],
    targetWindow: "",
    availableWindows: [],
    connected: false
  }
};

const defaultGlobalSettingsOption: InputOptionDefinition = {
  key: GLOBAL_SETTINGS_TASK_NAME,
  type: "input",
  label: GLOBAL_SETTINGS_TASK_NAME,
  inputs: []
};

const featureMetadataByEntry: Record<string, Pick<GameDefinition["features"][number], "id" | "description">> = {
  钓鱼: {
    id: "fish",
    description: "自动钓鱼、溜鱼、卖鱼买饵、鱼截图"
  },
  弹钢琴_keybord: {
    id: "piano",
    description: "MIDI 文件、键盘输入模式"
  },
  实时辅助: {
    id: "assist",
    description: "自动拾取"
  }
};

const parsedInterface = parseJsonc(interfaceJsonc);
const clientData = buildClientDataFromInterface(parsedInterface);

export const globalSettingsOption = clientData.globalSettingsOption;
export const globalSettingsDefaultValues = clientData.globalSettingsDefaultValues;
export const nteOptions = clientData.nteOptions;
export const initialGames = clientData.initialGames;

export function parseJsonc(text: string): MaaInterfaceConfig {
  return JSON.parse(stripJsoncComments(text)) as MaaInterfaceConfig;
}

export function buildClientDataFromInterface(config: MaaInterfaceConfig): ClientData {
  const optionDefinitions = buildOptionDefinitions(config.option ?? {});
  const globalSettingsOption = getGlobalSettingsOption(config, optionDefinitions);
  const globalSettingsDefaultValues = buildInputDefaultValues(globalSettingsOption);
  const featureTasks = (config.task ?? []).filter((task) => task.name !== GLOBAL_SETTINGS_TASK_NAME);
  const controllerNames = (config.controller ?? []).map((controller) => controller.name).filter(Boolean);
  const defaultControllerName = controllerNames[0] ?? "";

  const features = featureTasks.map((task, index) => {
    const entry = task.entry ?? task.name;
    const metadata = featureMetadataByEntry[entry];
    const optionKeys = task.option ?? [];

    return {
      id: metadata?.id ?? toStableId(entry, index),
      name: task.name,
      description: metadata?.description ?? optionKeys.join(" / "),
      configSummary: "",
      optionKeys,
      optionValues: buildDefaultOptionValues(optionKeys, optionDefinitions)
    };
  });

  const game: GameDefinition = {
    id: DEFAULT_GAME_ID,
    name: config.name ?? DEFAULT_GAME_ID,
    description: config.description,
    shortName: DEFAULT_GAME_SHORT_NAME,
    icon: DEFAULT_GAME_ICON,
    status: "ready",
    kind: "maa",
    controller: {
      controllerType: defaultControllerName,
      controllerTypes: controllerNames,
      targetWindow: "",
      availableWindows: [],
      connected: false
    },
    features
  };

  return {
    globalSettingsOption,
    globalSettingsDefaultValues,
    nteOptions: optionDefinitions,
    initialGames: [game, HS_GAME]
  };
}

function stripJsoncComments(text: string): string {
  let result = "";
  let inString = false;
  let quote = "";
  let escaped = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (inString) {
      result += char;
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        inString = false;
      }
      continue;
    }

    if (char === "\"" || char === "'") {
      inString = true;
      quote = char;
      result += char;
      continue;
    }

    if (char === "/" && next === "/") {
      while (index < text.length && text[index] !== "\n") index += 1;
      result += "\n";
      continue;
    }

    if (char === "/" && next === "*") {
      index += 2;
      while (index < text.length && !(text[index] === "*" && text[index + 1] === "/")) index += 1;
      index += 1;
      continue;
    }

    result += char;
  }

  return result;
}

function buildOptionDefinitions(maaOptions: Record<string, MaaOptionDefinition>): Record<string, OptionDefinition> {
  const optionDefinitions: Record<string, OptionDefinition> = {};

  for (const [key, option] of Object.entries(maaOptions)) {
    if (option.type === "switch") {
      optionDefinitions[key] = {
        key,
        type: "switch",
        label: option.label ?? key,
        description: option.description,
        defaultValue: option.default_case === "Yes",
        enabledOptionKeys: option.cases?.flatMap((caseDefinition) => caseDefinition.option ?? []),
        pipelineOverridesByValue: {
          true: option.cases?.find((caseDefinition) => caseDefinition.name === "Yes")?.pipeline_override,
          false: option.cases?.find((caseDefinition) => caseDefinition.name === "No")?.pipeline_override
        }
      };
      continue;
    }

    if (option.type === "select") {
      const cases = option.cases?.map((caseDefinition) => caseDefinition.label ?? caseDefinition.name) ?? [];
      const pipelineOverridesByCase = Object.fromEntries(
        (option.cases ?? [])
          .filter((caseDefinition) => caseDefinition.pipeline_override)
          .map((caseDefinition) => [
            caseDefinition.label ?? caseDefinition.name,
            caseDefinition.pipeline_override as PipelineOverride
          ])
      );

      optionDefinitions[key] = {
        key,
        type: "select",
        label: option.label ?? key,
        description: option.description,
        defaultValue: option.default_case ?? cases[0] ?? "",
        cases,
        pipelineOverridesByCase
      };
      continue;
    }

    optionDefinitions[key] = {
      key,
      type: "input",
      label: option.label ?? key,
      description: option.description,
      inputs: (option.inputs ?? []).map(toInputDefinition),
      pipelineOverride: option.pipeline_override
    };
  }

  return optionDefinitions;
}

function toInputDefinition(input: MaaInputDefinition): OptionInputDefinition {
  return {
    name: input.name,
    label: input.label ?? input.name,
    description: input.description,
    pipelineType: input.pipeline_type === "int" ? "int" : "string",
    defaultValue: input.default ?? ""
  };
}

function getGlobalSettingsOption(
  config: MaaInterfaceConfig,
  optionDefinitions: Record<string, OptionDefinition>
): InputOptionDefinition {
  const globalTask = config.task?.find((task) => task.name === GLOBAL_SETTINGS_TASK_NAME);
  const globalOptionKey = globalTask?.option?.[0] ?? GLOBAL_SETTINGS_TASK_NAME;
  const optionDefinition = optionDefinitions[globalOptionKey];

  return optionDefinition?.type === "input" ? optionDefinition : defaultGlobalSettingsOption;
}

function buildInputDefaultValues(optionDefinition: InputOptionDefinition): Record<string, OptionValue> {
  const values: Record<string, OptionValue> = {};

  for (const input of optionDefinition.inputs) {
    values[input.name] = input.defaultValue;
  }

  return values;
}

function buildDefaultOptionValues(
  optionKeys: string[],
  optionDefinitions: Record<string, OptionDefinition>
): Record<string, OptionValue> {
  const values: Record<string, OptionValue> = {};
  const visited = new Set<string>();

  for (const optionKey of optionKeys) {
    addDefaultOptionValue(optionKey, optionDefinitions, values, visited);
  }

  return values;
}

function addDefaultOptionValue(
  optionKey: string,
  optionDefinitions: Record<string, OptionDefinition>,
  values: Record<string, OptionValue>,
  visited: Set<string>
) {
  if (visited.has(optionKey)) return;
  visited.add(optionKey);

  const optionDefinition = optionDefinitions[optionKey];
  if (!optionDefinition) return;

  if (optionDefinition.type === "switch") {
    values[optionDefinition.key] = optionDefinition.defaultValue;
    for (const childOptionKey of optionDefinition.enabledOptionKeys ?? []) {
      addDefaultOptionValue(childOptionKey, optionDefinitions, values, visited);
    }
    return;
  }

  if (optionDefinition.type === "select") {
    values[optionDefinition.key] = optionDefinition.defaultValue;
    return;
  }

  for (const input of optionDefinition.inputs) {
    values[input.name] = input.defaultValue;
  }
}

function toStableId(value: string, index: number): string {
  const asciiId = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return asciiId || `feature-${index + 1}`;
}
