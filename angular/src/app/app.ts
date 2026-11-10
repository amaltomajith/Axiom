import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink, RouterOutlet } from '@angular/router';
import { ApiStatus, ApiStatusService } from './core/api-status.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly apiStatus = toSignal(inject(ApiStatusService).status$, { initialValue: 'checking' as ApiStatus });
}
