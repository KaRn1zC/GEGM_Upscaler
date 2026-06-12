import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // src-tauri/target : artefacts de build Rust locaux (JS minifié généré
  // par tauri-codegen) — jamais versionnés, mais le glob les attrape
  // quand un build desktop a tourné sur la machine.
  globalIgnores(['dist', 'coverage', 'src-tauri/target']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Aligne eslint sur la convention TypeScript noUnusedParameters :
      // un préfixe `_` marque un paramètre volontairement non utilisé
      // (utile pour respecter une signature d'interface sans consommer l'arg).
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
    },
  },
  {
    // Primitives shadcn/ui — exportent à la fois des composants et des
    // variants (cva). La règle react-refresh/only-export-components
    // n'a pas de sens ici car ces fichiers sont copy-paste depuis shadcn
    // et doivent rester identiques au registry officiel.
    files: ['src/components/ui/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
