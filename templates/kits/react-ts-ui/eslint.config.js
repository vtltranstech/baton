// Sensors: the rules come from config/sensors/eslint-sensors.json (a copy of baton sensors/), unchanged.
// Components and hooks get `rules`; the API client module gets `apiClientRules`, the only place fetch is allowed.
import { readFileSync } from "node:fs";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const sensors = JSON.parse(readFileSync(new URL("./config/sensors/eslint-sensors.json", import.meta.url)));

export default tseslint.config(
  { ignores: ["dist/", "coverage/"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { parser: tseslint.parser },
    plugins: { "@typescript-eslint": tseslint.plugin, "react-hooks": reactHooks },
    rules: sensors.rules,
  },
  { files: ["src/api/**/*.ts"], rules: sensors.apiClientRules },
);
