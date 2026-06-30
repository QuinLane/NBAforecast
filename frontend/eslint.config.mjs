import tseslint from "typescript-eslint";

export default tseslint.config(
  ...tseslint.configs.recommended,
  {
    ignores: [
      "src/lib/api-client/schema.d.ts",
      ".next/**",
      "node_modules/**",
    ],
  },
);
