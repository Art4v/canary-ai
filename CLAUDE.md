# Instructions for Claude Instances

These rules apply to every Claude instance working in this repository.

## 1. Keep the README up to date

After completing every prompt or task, update `README.md` at the repo root to reflect any changes:

- New features, endpoints, components, hooks, or utilities must be documented
- Removed or renamed items must be cleaned up from the README
- The **Project Structure** tree must stay accurate
- The **Tech Stack** table must list any newly added dependencies

## 2. Comment all code extensively

When writing or modifying code, add thorough inline comments:

- Every function and component must have a comment block explaining its purpose, parameters, and return value
- Non-obvious logic, algorithms, and business rules must have step-by-step explanatory comments
- CSS files should have section headers and comments on any non-trivial rule
- Magic numbers, environment-specific values, and thresholds must be annotated with their reasoning
- Keep comments current — when changing code, update the surrounding comments to match

## 3. Supabase Database Schema

Reference schema for all four tables. **Do not run this SQL directly** — it is for context only.

```sql
-- Users — core account table; username and email are unique; api_key stores a bcrypt hash (nullable, exactly 60 chars)
-- trading_style is a USER-DEFINED enum with values: balanced, risk_averse, risk-aggressive (nullable)
-- memory stores the chatbot's persistent session memory as free-form text (nullable)
-- preferences stores the chatbot's collected investment preferences as JSONB (nullable)
CREATE TABLE public.users (
  user_id uuid NOT NULL DEFAULT gen_random_uuid(),
  username character varying NOT NULL UNIQUE,
  email character varying NOT NULL UNIQUE,
  password_hash text NOT NULL,
  api_key text DEFAULT NULL,
  trading_style USER-DEFINED DEFAULT NULL,
  memory text DEFAULT NULL,
  preferences jsonb DEFAULT NULL,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT users_pkey PRIMARY KEY (user_id),
  CONSTRAINT users_api_key_length CHECK (length(api_key) = 60)
);

-- Portfolios — one per user; tracks cash and capital totals
CREATE TABLE public.portfolios (
  portfolio_id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL UNIQUE,
  cash_reserve numeric NOT NULL DEFAULT 0.00,
  total_capital_invested numeric NOT NULL DEFAULT 0.00,
  current_portfolio_value numeric NOT NULL DEFAULT 0.00,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT portfolios_pkey PRIMARY KEY (portfolio_id),
  CONSTRAINT portfolios_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id)
);

-- Holdings — per-ticker positions within a portfolio
CREATE TABLE public.holdings (
  holding_id uuid NOT NULL DEFAULT gen_random_uuid(),
  portfolio_id uuid NOT NULL,
  ticker character varying NOT NULL,
  quantity numeric NOT NULL DEFAULT 0,
  average_buy_price numeric NOT NULL DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT holdings_pkey PRIMARY KEY (holding_id),
  CONSTRAINT holdings_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id)
);

-- Transactions — buy/sell execution log within a portfolio
CREATE TABLE public.transactions (
  transaction_id uuid NOT NULL DEFAULT gen_random_uuid(),
  portfolio_id uuid NOT NULL,
  ticker character varying NOT NULL,
  tx_type USER-DEFINED NOT NULL,
  quantity numeric NOT NULL,
  price_per_unit numeric NOT NULL,
  total_amount numeric NOT NULL,
  executed_at timestamp with time zone DEFAULT now(),
  CONSTRAINT transactions_pkey PRIMARY KEY (transaction_id),
  CONSTRAINT transactions_portfolio_id_fkey FOREIGN KEY (portfolio_id) REFERENCES public.portfolios(portfolio_id)
);
```

**Key relationships:** `users` → `portfolios` (1:1 via `user_id`) → `holdings` / `transactions` (1:many via `portfolio_id`).
