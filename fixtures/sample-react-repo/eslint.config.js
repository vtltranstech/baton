import { readFileSync } from "node:fs";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const sensors = JSON.parse(readFileSync(new URL("./config/sensors/eslint-sensors.json", import.meta.url)));

export default tseslint.config(
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { parser: tseslint.parser },
    plugins: { "@typescript-eslint": tseslint.plugin, "react-hooks": reactHooks },
    rules: sensors.rules,
  },
  { files: ["src/api/**/*.ts"], rules: sensors.apiClientRules },
);
