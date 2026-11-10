import { bootstrapApplication } from '@angular/platform-browser';
import { App } from './app/app';
import { appConfig } from './app/app.config';
import { loadApiBase } from './app/core/config';

loadApiBase()
  .then(apiBase => bootstrapApplication(App, appConfig(apiBase)))
  .catch((err: unknown) => console.error(err));
