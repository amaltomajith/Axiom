# Stock Prediction Dashboard

AI-powered stock analysis tool with real-time data, technical indicators, backtesting, and paper trading.

## Tech Stack

- **Frontend:** React + TypeScript + Vite + Tailwind CSS + shadcn/ui
- **Backend:** Lovable Cloud (Supabase) – Edge Functions, Auth
- **Charts:** Recharts
- **Animations:** Framer Motion

## Features

- 📈 Real-time stock price charts (OHLCV)
- 🤖 AI prediction models (LSTM, Random Forest, ARIMA, Sentiment, Ensemble)
- 📰 Live news feed with sentiment analysis
- 🔔 Technical signal indicators (RSI, MACD, Bollinger Bands)
- 📊 Backtesting engine for strategy validation
- 💰 Paper trading simulator
- 👀 Watchlist management

## Getting Started

### Prerequisites

- Node.js 18+ & npm

### Installation

```bash
git clone <YOUR_GIT_URL>
cd <YOUR_PROJECT_NAME>
npm install
npm run dev
```

### Environment Variables

Create a `.env` file in the root:

```env
VITE_SUPABASE_URL=https://yxwdegyxirikgochhygi.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<your-anon-key>
VITE_SUPABASE_PROJECT_ID=yxwdegyxirikgochhygi
```

## Deploy to Vercel

1. Push this repo to GitHub
2. Import the repo in [Vercel](https://vercel.com)
3. Set **Build Command** to `npm run build`
4. Set **Output Directory** to `dist`
5. Add the environment variables above in **Settings → Environment Variables**
6. Deploy 🚀

The included `vercel.json` handles SPA routing automatically.

## Project Structure

```
src/
├── components/       # UI components (chart, panels, tabs)
├── hooks/            # Custom React hooks
├── integrations/     # Supabase client & types
├── lib/              # Business logic (indicators, models, API)
├── pages/            # Route pages
supabase/
├── functions/        # Edge functions (stock-data, stock-news)
```

## License

MIT
