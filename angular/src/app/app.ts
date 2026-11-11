import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink, RouterOutlet } from '@angular/router';
import { ApiStatus, ApiStatusService } from './core/api-status.service';
import { HUB_URL } from './core/config';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly hubUrl = inject(HUB_URL);
  protected readonly apiStatus = toSignal(inject(ApiStatusService).status$, { initialValue: 'checking' as ApiStatus });
}
