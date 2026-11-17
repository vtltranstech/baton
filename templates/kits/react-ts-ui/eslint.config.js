// Sensors: the rules come from config/sensors/eslint-sensors.json (a copy of baton sensors/), unchanged.
// Components and hooks get `rules`; the API client module gets `apiClientRules`, the only place fetch is allowed.
// UI stories (contracts/ui-stories.md section 8): jsx-a11y, and no direct import of what the org's component
// library wraps (config/ui-library.json, kept equal to profile/project.md ui.library.forbid).
import { readFileSync } from "node:fs";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const sensors = JSON.parse(readFileSync(new URL("./config/sensors/eslint-sensors.json", import.meta.url)));
const library = JSON.parse(readFileSync(new URL("./config/ui-library.json", import.meta.url)));
const restricted = {
  "no-restricted-imports": [
    "error",
    {
      patterns: library.forbid.map((group) => ({
        group: [group],
        message: `Build screens from ${library.import.join(", ")}; it wraps ${group}.`,
      })),
    },
  ],
};

export default tseslint.config(
  { ignores: ["dist/", "coverage/"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { parser: tseslint.parser },
    plugins: { "@typescript-eslint": tseslint.plugin, "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    rules: { ...sensors.rules, ...jsxA11y.flatConfigs.recommended.rules, ...restricted },
  },
  { files: ["src/api/**/*.ts"], rules: sensors.apiClientRules },
);
