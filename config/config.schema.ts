import * as path from 'path';
import * as fs from 'fs';
import { ConfigSchema, AppConfig } from '../src/types/config';

export function loadConfig(configPath?: string): AppConfig {
  const resolvedPath = configPath || path.resolve(__dirname, 'config.json');
  const raw = JSON.parse(fs.readFileSync(resolvedPath, 'utf-8'));
  return ConfigSchema.parse(raw);
}
