/*
 * prediction.cpp — CSV loader and parser for stock data
 *
 * Loads minute-level stock data from CSV files in test_data/,
 * parses timestamps and numeric fields into StockRow structs,
 * sorts by timestamp, and prints a summary for verification.
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>
#include <ctime>
#include <iomanip>
#include <cstdio>
#include <cmath>
#include <random>
#include <map>
#include <set>

/* Represents a single portfolio on the efficient frontier.
 * Stores the weight allocation, expected return, variance, and
 * standard deviation (risk) for one randomly sampled portfolio. */
struct Portfolio {
    std::vector<double> weights;  // weight per stock, sums to 1.0
    double expected_return;       // w^T * mean_returns
    double variance;              // w^T * Σ * w
    double std_dev;               // sqrt(variance) — portfolio risk
};

/* Represents the share allocation for a single stock in the portfolio.
 * Converts an optimal weight into a concrete number of whole shares
 * given the current price and total investable capital. */
struct Allocation {
    std::string ticker;       // stock symbol
    double weight;            // optimal weight from Sharpe maximization
    double current_price;     // latest price used for allocation
    double target_dollars;    // weight * investable capital
    int shares;               // floor(target_dollars / current_price)
    double invested;          // shares * current_price (actual dollars used)
    double remainder;         // target_dollars - invested (rounding leftover)
};

/* Represents a stock currently held in the portfolio.
 * Tracks the number of shares, average price, and last update time.
 * Used to compare current positions against target allocation. */
struct Holding {
    std::string ticker;       // stock symbol
    int shares;               // current whole shares held
    double avg_price;         // price at last update (for audit trail)
    std::string last_updated; // timestamp of last update
};

/* Represents a single trade action computed by comparing current
 * holdings against the target allocation from the optimizer.
 * delta > 0 means buy, delta < 0 means sell, delta == 0 means hold. */
struct Trade {
    std::string ticker;      // stock symbol
    int current_shares;      // shares held before trade
    int target_shares;       // shares the optimizer wants
    int delta;               // target - current (+ = buy, - = sell, 0 = hold)
    double current_price;    // price used for cost calculation
    double cost;             // delta * current_price (negative for sells)
    std::string action;      // "BUY", "SELL", or "HOLD"
};

/* Represents a single row of stock data from a CSV file. */
struct StockRow {
    std::tm timestamp;       // parsed datetime (timezone offset discarded)
    std::string ticker;      // stock symbol, e.g. "AAPL"
    double current_price;    // price at this minute
    double day_high;         // intraday high so far
    double day_low;          // intraday low so far
    double volume;           // cumulative volume
    double market_cap;       // market capitalisation
};

/*
 * parse_timestamp — extracts datetime from a string like
 *   "2026-03-12 09:30:00-04:00"
 *
 * We only parse the "YYYY-MM-DD HH:MM:SS" portion and ignore
 * the timezone offset since all data shares the same tz (-04:00).
 *
 * @param ts_str  the raw timestamp string from the CSV
 * @return        a std::tm struct populated with the parsed datetime
 */
std::tm parse_timestamp(const std::string& ts_str) {
    std::tm tm = {};
    // sscanf is used here instead of std::get_time for reliable
    // cross-platform parsing of the "YYYY-MM-DD HH:MM:SS" format
    std::sscanf(ts_str.c_str(), "%d-%d-%d %d:%d:%d",
                &tm.tm_year, &tm.tm_mon, &tm.tm_mday,
                &tm.tm_hour, &tm.tm_min, &tm.tm_sec);
    // std::tm year is years since 1900, month is 0-based
    tm.tm_year -= 1900;
    tm.tm_mon -= 1;
    // let mktime figure out DST
    tm.tm_isdst = -1;
    return tm;
}

/*
 * format_timestamp — converts a std::tm back to a readable string
 *
 * @param tm  the timestamp to format
 * @return    string in "YYYY-MM-DD HH:MM:SS" format
 */
std::string format_timestamp(const std::tm& tm) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%04d-%02d-%02d %02d:%02d:%02d",
                  tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday,
                  tm.tm_hour, tm.tm_min, tm.tm_sec);
    return std::string(buf);
}

/*
 * to_time_t — converts a std::tm to time_t without mutating the input.
 *
 * mktime requires a non-const pointer and may normalize the struct,
 * so we work on a copy. tm_isdst is set to -1 to let the system
 * determine DST status automatically.
 *
 * @param tm  the timestamp to convert
 * @return    the corresponding time_t value
 */
time_t to_time_t(std::tm tm) {
    tm.tm_isdst = -1;
    return std::mktime(&tm);
}

/*
 * load_csv — reads a CSV file and returns a sorted vector of StockRow.
 *
 * Expected CSV header:
 *   timestamp,ticker,current_price,day_high,day_low,volume,market_cap
 *
 * @param filepath  path to the CSV file (relative or absolute)
 * @return          vector of StockRow sorted by timestamp ascending
 */
std::vector<StockRow> load_csv(const std::string& filepath) {
    std::vector<StockRow> rows;
    std::ifstream file(filepath);

    if (!file.is_open()) {
        std::cerr << "Error: could not open file: " << filepath << std::endl;
        return rows;
    }

    std::string line;

    // skip the header line
    std::getline(file, line);

    // parse each data row
    while (std::getline(file, line)) {
        // skip empty lines
        if (line.empty()) continue;

        std::istringstream ss(line);
        std::string token;
        StockRow row;

        // field 1: timestamp (contains a comma-free datetime string)
        std::getline(ss, token, ',');
        row.timestamp = parse_timestamp(token);

        // field 2: ticker symbol
        std::getline(ss, row.ticker, ',');

        // field 3: current_price
        std::getline(ss, token, ',');
        row.current_price = std::stod(token);

        // field 4: day_high
        std::getline(ss, token, ',');
        row.day_high = std::stod(token);

        // field 5: day_low
        std::getline(ss, token, ',');
        row.day_low = std::stod(token);

        // field 6: volume
        std::getline(ss, token, ',');
        row.volume = std::stod(token);

        // field 7: market_cap
        std::getline(ss, token, ',');
        row.market_cap = std::stod(token);

        rows.push_back(row);
    }

    file.close();

    // sort rows by timestamp ascending using mktime for comparison
    std::sort(rows.begin(), rows.end(),
              [](const StockRow& a, const StockRow& b) {
                  // mktime normalizes the tm struct and returns time_t for comparison
                  std::tm ta = a.timestamp;
                  std::tm tb = b.timestamp;
                  return std::mktime(&ta) < std::mktime(&tb);
              });

    return rows;
}

/*
 * print_summary — prints a quick summary of a loaded stock dataset.
 *
 * Displays the ticker, total row count, and the first/last timestamps
 * so we can verify the data was loaded and sorted correctly.
 *
 * @param rows  the vector of StockRow to summarize
 */
void print_summary(const std::vector<StockRow>& rows) {
    if (rows.empty()) {
        std::cout << "(empty dataset)" << std::endl;
        return;
    }

    std::cout << "Ticker:    " << rows.front().ticker << std::endl;
    std::cout << "Rows:      " << rows.size() << std::endl;

    // show first and last timestamp to confirm sort order
    std::tm first = rows.front().timestamp;
    std::tm last  = rows.back().timestamp;
    std::cout << "First:     " << format_timestamp(first) << std::endl;
    std::cout << "Last:      " << format_timestamp(last) << std::endl;
    std::cout << std::endl;
}

/*
 * align_timestamps — aligns multiple stock vectors to a common timestamp index.
 *
 * Different stocks may have different numbers of rows due to gaps in
 * low-liquidity trading. This function builds the union of all timestamps
 * across all stocks, then for each stock produces a row at every timestamp:
 *   - If the stock has original data at that timestamp, use it.
 *   - Otherwise, forward-fill from the last known row (copies all fields).
 *   - Timestamps before every stock's first data point are excluded
 *     (global_start = latest first-timestamp across all stocks).
 *
 * The input vectors are modified in place to contain the aligned data.
 *
 * @param stocks              pointers to each stock's row vector (modified in place)
 * @param original_sizes_out  output: the original size of each vector before alignment
 */
void align_timestamps(std::vector<std::vector<StockRow>*> stocks,
                      std::vector<size_t>& original_sizes_out) {
    original_sizes_out.clear();

    // Step 1: Build a map from time_t -> StockRow for each stock,
    // and collect the union of all timestamps into a set.
    std::set<time_t> all_timestamps;
    std::vector<std::map<time_t, StockRow>> stock_maps(stocks.size());

    for (size_t i = 0; i < stocks.size(); ++i) {
        original_sizes_out.push_back(stocks[i]->size());
        for (const auto& row : *stocks[i]) {
            time_t t = to_time_t(row.timestamp);
            stock_maps[i][t] = row;
            all_timestamps.insert(t);
        }
    }

    // Step 2: Filter to valid_timestamps — keep only timestamps where at least
    // one stock has original data. This avoids creating rows that would be
    // entirely forward-filled across all stocks.
    std::vector<time_t> valid_timestamps;
    for (time_t t : all_timestamps) {
        bool any_has_data = false;
        for (size_t i = 0; i < stocks.size(); ++i) {
            if (stock_maps[i].count(t)) {
                any_has_data = true;
                break;
            }
        }
        if (any_has_data) {
            valid_timestamps.push_back(t);
        }
    }

    // Step 2b: Compute global_start — the latest "first timestamp" across all
    // stocks. This is the earliest point where every stock has data, so we never
    // need zero-fill placeholders (which would corrupt return calculations).
    time_t global_start = 0;
    for (size_t i = 0; i < stocks.size(); ++i) {
        if (!stock_maps[i].empty()) {
            time_t first = stock_maps[i].begin()->first;
            if (first > global_start) {
                global_start = first;
            }
        }
    }

    // Remove any timestamps before global_start so every stock is guaranteed
    // to have at least its first row at or before the series begins.
    valid_timestamps.erase(
        std::remove_if(valid_timestamps.begin(), valid_timestamps.end(),
                       [global_start](time_t t) { return t < global_start; }),
        valid_timestamps.end());

    // Step 3: For each stock, iterate through valid_timestamps and produce
    // aligned rows using forward-fill for missing data points.
    for (size_t i = 0; i < stocks.size(); ++i) {
        std::vector<StockRow> aligned;
        aligned.reserve(valid_timestamps.size());

        bool has_last_known = false;
        StockRow last_known = {};

        for (time_t t : valid_timestamps) {
            if (stock_maps[i].count(t)) {
                // Stock has original data at this timestamp — use it directly
                last_known = stock_maps[i][t];
                has_last_known = true;
                aligned.push_back(last_known);
            } else {
                // No data at this timestamp — forward-fill from last known row.
                // Copy all fields (price, volume, market_cap) and update timestamp.
                // Note: has_last_known is always true here because we trimmed
                // timestamps before global_start (every stock's first row).
                StockRow filled = last_known;
                // Platform-safe conversion from time_t to std::tm.
                // std::localtime returns a pointer to a static buffer
                // which is not thread-safe; use the platform-specific
                // reentrant variant instead.
                std::tm new_tm = {};
#ifdef _WIN32
                localtime_s(&new_tm, &t);
#else
                localtime_r(&t, &new_tm);
#endif
                filled.timestamp = new_tm;
                aligned.push_back(filled);
            }
        }

        // Replace the original vector with the aligned result
        *stocks[i] = std::move(aligned);
    }
}

/*
 * print_alignment_summary — prints how many rows were filled per stock.
 *
 * Shows the common timestamp count and, for each stock, the original row count,
 * aligned row count, and how many rows were forward-filled.
 *
 * @param labels          display names for each stock (e.g. "AAPL")
 * @param original_sizes  row counts before alignment
 * @param aligned_sizes   row counts after alignment
 */
void print_alignment_summary(const std::vector<std::string>& labels,
                             const std::vector<size_t>& original_sizes,
                             const std::vector<size_t>& aligned_sizes) {
    std::cout << "=== Alignment Summary ===" << std::endl;

    // All aligned sizes should be identical; use the first as the common count
    if (!aligned_sizes.empty()) {
        std::cout << "Common timestamps: " << aligned_sizes[0] << std::endl;
    }

    for (size_t i = 0; i < labels.size(); ++i) {
        size_t filled = aligned_sizes[i] - original_sizes[i];
        std::cout << "  " << labels[i] << ": "
                  << original_sizes[i] << " original -> "
                  << aligned_sizes[i] << " aligned ("
                  << filled << " filled)" << std::endl;
    }
    std::cout << std::endl;
}

/*
 * compute_returns — calculates per-minute simple returns from an aligned
 * stock series.
 *
 * For each consecutive pair of rows, computes:
 *   r_t = (current_price_t - current_price_{t-1}) / current_price_{t-1}
 *
 * The first element is always 0.0 (no prior price to compare against),
 * so the returned vector has the same length as the input — keeping
 * indices aligned with the stock rows and timestamps.
 *
 * @param rows  aligned stock data (must have at least 1 row)
 * @return      vector of per-minute returns, same length as rows
 */
std::vector<double> compute_returns(const std::vector<StockRow>& rows) {
    std::vector<double> returns(rows.size(), 0.0);
    // Start at index 1; index 0 stays 0.0 (no previous price)
    for (size_t t = 1; t < rows.size(); ++t) {
        double prev = rows[t - 1].current_price;
        // Guard against division by zero (shouldn't happen with real
        // price data, but protects against malformed CSVs)
        if (prev != 0.0) {
            returns[t] = (rows[t].current_price - prev) / prev;
        }
    }
    return returns;
}

/*
 * print_returns_summary — prints basic statistics for a returns vector.
 *
 * Shows the ticker label, total return count, and min/max values
 * for quick verification.
 *
 * @param label    stock ticker label (e.g. "AAPL")
 * @param returns  the per-minute returns vector
 */
void print_returns_summary(const std::string& label,
                           const std::vector<double>& returns) {
    if (returns.empty()) return;

    // Find min and max returns (skip index 0 which is always 0.0)
    double min_ret = returns[1];
    double max_ret = returns[1];
    for (size_t i = 2; i < returns.size(); ++i) {
        if (returns[i] < min_ret) min_ret = returns[i];
        if (returns[i] > max_ret) max_ret = returns[i];
    }

    std::cout << "  " << label << ": "
              << returns.size() - 1 << " returns, "
              << "min=" << min_ret << ", max=" << max_ret
              << std::endl;
}

/*
 * compute_mean_returns — computes the arithmetic mean return for each stock.
 *
 * Skips index 0 (which is always 0.0, no prior price) and averages
 * indices 1..N-1, giving the true mean per-minute return.
 *
 * @param all_returns  vector of return vectors, one per stock
 * @return             vector of mean returns, one per stock
 */
std::vector<double> compute_mean_returns(
        const std::vector<std::vector<double>>& all_returns) {
    std::vector<double> means;
    for (const auto& returns : all_returns) {
        double sum = 0.0;
        // Skip index 0 (always 0.0 — no previous price to compare)
        for (size_t i = 1; i < returns.size(); ++i) {
            sum += returns[i];
        }
        // N-1 actual returns (indices 1..N-1)
        double mean = (returns.size() > 1) ? sum / (returns.size() - 1) : 0.0;
        means.push_back(mean);
    }
    return means;
}

/*
 * compute_covariance_matrix — builds the NxN sample covariance matrix
 * from N stocks' return vectors.
 *
 * Uses Bessel's correction (divides by n-1) for an unbiased estimate.
 * Skips index 0 of each return vector (always 0.0).
 *
 * The matrix is symmetric: cov(i,j) == cov(j,i). Diagonal entries
 * are each stock's variance.
 *
 * @param all_returns  vector of return vectors (one per stock, all same length)
 * @param means        pre-computed mean returns (one per stock)
 * @return             NxN covariance matrix as vector<vector<double>>
 */
std::vector<std::vector<double>> compute_covariance_matrix(
        const std::vector<std::vector<double>>& all_returns,
        const std::vector<double>& means) {
    size_t n_stocks = all_returns.size();
    // Number of actual return observations (skip index 0)
    size_t n_obs = all_returns[0].size() - 1;

    // Initialize NxN matrix with zeros
    std::vector<std::vector<double>> cov(n_stocks,
                                          std::vector<double>(n_stocks, 0.0));

    for (size_t i = 0; i < n_stocks; ++i) {
        // Only compute upper triangle + diagonal; mirror for lower triangle
        for (size_t j = i; j < n_stocks; ++j) {
            double sum = 0.0;
            // Iterate over actual returns (indices 1..N-1)
            for (size_t t = 1; t <= n_obs; ++t) {
                sum += (all_returns[i][t] - means[i]) *
                       (all_returns[j][t] - means[j]);
            }
            // Bessel's correction: divide by n-1
            double covariance = sum / (n_obs - 1);
            cov[i][j] = covariance;
            cov[j][i] = covariance;  // symmetric
        }
    }

    return cov;
}

/*
 * print_covariance_summary — prints the mean return vector and the
 * full covariance matrix in a labelled grid.
 *
 * @param labels  stock ticker labels (e.g. {"AAPL", "BOBS", "MSFT"})
 * @param means   mean return per stock
 * @param cov     NxN covariance matrix
 */
void print_covariance_summary(const std::vector<std::string>& labels,
                               const std::vector<double>& means,
                               const std::vector<std::vector<double>>& cov) {
    // Print mean returns
    std::cout << "=== Mean Returns ===" << std::endl;
    for (size_t i = 0; i < labels.size(); ++i) {
        std::cout << "  " << labels[i] << ": " << means[i] << std::endl;
    }
    std::cout << std::endl;

    // Print covariance matrix with row/column labels
    std::cout << "=== Covariance Matrix ===" << std::endl;
    // Column header row
    std::cout << "          ";
    for (const auto& label : labels) {
        std::cout << std::setw(14) << label;
    }
    std::cout << std::endl;

    // Data rows
    for (size_t i = 0; i < labels.size(); ++i) {
        std::cout << "  " << std::setw(6) << labels[i];
        for (size_t j = 0; j < labels.size(); ++j) {
            std::cout << std::setw(14) << std::scientific
                      << std::setprecision(6) << cov[i][j];
        }
        std::cout << std::endl;
    }
    std::cout << std::endl;
}

/*
 * generate_random_weights — produces a random weight vector that sums to 1.0.
 *
 * Uses the uniform-then-normalize method: draw N uniform(0,1) samples,
 * then divide each by their sum. All weights are non-negative and sum
 * to exactly 1.0, satisfying the long-only fully-invested constraint.
 *
 * @param n    number of assets (length of weight vector)
 * @param rng  Mersenne Twister RNG, passed by reference for state continuity
 * @return     vector of n weights summing to 1.0
 */
std::vector<double> generate_random_weights(size_t n, std::mt19937& rng) {
    std::uniform_real_distribution<double> dist(0.0, 1.0);
    std::vector<double> w(n);
    double sum = 0.0;
    for (size_t i = 0; i < n; ++i) {
        w[i] = dist(rng);
        sum += w[i];
    }
    // Normalize so weights sum to 1.0
    for (size_t i = 0; i < n; ++i) {
        w[i] /= sum;
    }
    return w;
}

/*
 * compute_portfolio_return — computes the expected return of a portfolio.
 *
 * Calculates the dot product w^T * mean_returns, which gives the
 * weighted average of the individual stock mean returns.
 *
 * @param weights       portfolio weight vector (length N)
 * @param mean_returns  mean return per stock (length N)
 * @return              portfolio expected return (scalar)
 */
double compute_portfolio_return(const std::vector<double>& weights,
                                const std::vector<double>& mean_returns) {
    double ret = 0.0;
    for (size_t i = 0; i < weights.size(); ++i) {
        ret += weights[i] * mean_returns[i];
    }
    return ret;
}

/*
 * compute_portfolio_variance — computes the variance of a portfolio.
 *
 * Evaluates the quadratic form w^T * Σ * w, where Σ is the covariance
 * matrix. This captures both individual stock variances and the
 * diversification benefit from correlations between stocks.
 *
 * @param weights     portfolio weight vector (length N)
 * @param cov_matrix  NxN covariance matrix
 * @return            portfolio variance (scalar)
 */
double compute_portfolio_variance(const std::vector<double>& weights,
                                  const std::vector<std::vector<double>>& cov_matrix) {
    double var = 0.0;
    for (size_t i = 0; i < weights.size(); ++i) {
        for (size_t j = 0; j < weights.size(); ++j) {
            var += weights[i] * weights[j] * cov_matrix[i][j];
        }
    }
    return var;
}

/*
 * generate_frontier_portfolios — samples random portfolios for the
 * efficient frontier.
 *
 * Generates n_samples random weight combinations, computes each
 * portfolio's expected return, variance, and standard deviation,
 * and returns them as a vector of Portfolio structs. Uses a fixed
 * seed (42) for reproducible results during development.
 *
 * @param mean_returns  mean return per stock (length N)
 * @param cov_matrix    NxN covariance matrix
 * @param n_samples     number of random portfolios to generate (default 1000)
 * @return              vector of Portfolio structs with computed metrics
 */
std::vector<Portfolio> generate_frontier_portfolios(
        const std::vector<double>& mean_returns,
        const std::vector<std::vector<double>>& cov_matrix,
        int n_samples = 1000) {
    size_t n_assets = mean_returns.size();
    // Fixed seed for reproducible results during development
    std::mt19937 rng(42);

    std::vector<Portfolio> portfolios;
    portfolios.reserve(n_samples);

    for (int s = 0; s < n_samples; ++s) {
        Portfolio p;
        p.weights = generate_random_weights(n_assets, rng);
        p.expected_return = compute_portfolio_return(p.weights, mean_returns);
        p.variance = compute_portfolio_variance(p.weights, cov_matrix);
        p.std_dev = std::sqrt(p.variance);
        portfolios.push_back(p);
    }

    return portfolios;
}

/*
 * print_frontier_summary — prints statistics about the generated frontier
 * portfolios.
 *
 * Reports total portfolios generated, identifies the minimum-variance
 * (lowest risk) portfolio and the maximum-return portfolio, and prints
 * their weight allocations and risk/return metrics.
 *
 * @param labels      stock ticker labels (e.g. {"AAPL", "BOBS", "MSFT"})
 * @param portfolios  vector of generated Portfolio structs
 */
void print_frontier_summary(const std::vector<std::string>& labels,
                            const std::vector<Portfolio>& portfolios) {
    if (portfolios.empty()) {
        std::cout << "(no portfolios generated)" << std::endl;
        return;
    }

    std::cout << "=== Frontier Summary ===" << std::endl;
    std::cout << "Portfolios generated: " << portfolios.size() << std::endl;
    std::cout << std::endl;

    // Find the portfolio with minimum variance (lowest risk)
    size_t min_var_idx = 0;
    for (size_t i = 1; i < portfolios.size(); ++i) {
        if (portfolios[i].variance < portfolios[min_var_idx].variance) {
            min_var_idx = i;
        }
    }

    // Find the portfolio with maximum expected return
    size_t max_ret_idx = 0;
    for (size_t i = 1; i < portfolios.size(); ++i) {
        if (portfolios[i].expected_return > portfolios[max_ret_idx].expected_return) {
            max_ret_idx = i;
        }
    }

    // Print min-variance portfolio details
    const Portfolio& mv = portfolios[min_var_idx];
    std::cout << "Min-Variance Portfolio:" << std::endl;
    std::cout << "  Weights: ";
    for (size_t i = 0; i < labels.size(); ++i) {
        std::cout << labels[i] << "=" << std::fixed << std::setprecision(4)
                  << mv.weights[i];
        if (i + 1 < labels.size()) std::cout << ", ";
    }
    std::cout << std::endl;
    std::cout << "  Expected Return: " << std::scientific << std::setprecision(6)
              << mv.expected_return << std::endl;
    std::cout << "  Std Dev (Risk):  " << std::scientific << std::setprecision(6)
              << mv.std_dev << std::endl;
    std::cout << std::endl;

    // Print max-return portfolio details
    const Portfolio& mr = portfolios[max_ret_idx];
    std::cout << "Max-Return Portfolio:" << std::endl;
    std::cout << "  Weights: ";
    for (size_t i = 0; i < labels.size(); ++i) {
        std::cout << labels[i] << "=" << std::fixed << std::setprecision(4)
                  << mr.weights[i];
        if (i + 1 < labels.size()) std::cout << ", ";
    }
    std::cout << std::endl;
    std::cout << "  Expected Return: " << std::scientific << std::setprecision(6)
              << mr.expected_return << std::endl;
    std::cout << "  Std Dev (Risk):  " << std::scientific << std::setprecision(6)
              << mr.std_dev << std::endl;
    std::cout << std::endl;
}

/*
 * find_optimal_portfolio — selects the portfolio with the highest Sharpe ratio.
 *
 * Sharpe ratio = (expected_return - risk_free_rate) / std_dev
 * Skips any portfolio with std_dev == 0 to avoid division by zero.
 *
 * @param portfolios      vector of frontier Portfolio structs
 * @param risk_free_rate  the risk-free rate (default 0.0 for per-minute returns,
 *                        where the per-minute risk-free rate is negligible)
 * @return                index of the portfolio with the highest Sharpe ratio
 */
size_t find_optimal_portfolio(const std::vector<Portfolio>& portfolios,
                              double risk_free_rate = 0.0) {
    size_t best_idx = 0;
    double best_sharpe = -1e18;  // start with a very low value

    for (size_t i = 0; i < portfolios.size(); ++i) {
        // Skip portfolios with zero risk — Sharpe ratio is undefined
        if (portfolios[i].std_dev == 0.0) continue;

        // Sharpe = excess return / risk
        double sharpe = (portfolios[i].expected_return - risk_free_rate)
                        / portfolios[i].std_dev;

        if (sharpe > best_sharpe) {
            best_sharpe = sharpe;
            best_idx = i;
        }
    }

    return best_idx;
}

/*
 * print_optimal_portfolio — prints the optimal portfolio's Sharpe ratio,
 * weight allocation, expected return, and standard deviation.
 *
 * @param labels      stock ticker labels (e.g. {"AAPL", "BOBS", "MSFT"})
 * @param portfolios  vector of frontier Portfolio structs
 * @param optimal_idx index of the optimal portfolio in the vector
 */
void print_optimal_portfolio(const std::vector<std::string>& labels,
                             const std::vector<Portfolio>& portfolios,
                             size_t optimal_idx) {
    const Portfolio& op = portfolios[optimal_idx];

    // Compute the Sharpe ratio for display (r_f = 0.0)
    double sharpe = (op.std_dev != 0.0)
                    ? op.expected_return / op.std_dev
                    : 0.0;

    std::cout << "=== Optimal Portfolio (Max Sharpe) ===" << std::endl;
    std::cout << "  Sharpe Ratio:    " << std::fixed << std::setprecision(6)
              << sharpe << std::endl;

    // Print weight allocation per stock
    std::cout << "  Weights: ";
    for (size_t i = 0; i < labels.size(); ++i) {
        std::cout << labels[i] << "=" << std::fixed << std::setprecision(4)
                  << op.weights[i];
        if (i + 1 < labels.size()) std::cout << ", ";
    }
    std::cout << std::endl;

    std::cout << "  Expected Return: " << std::scientific << std::setprecision(6)
              << op.expected_return << std::endl;
    std::cout << "  Std Dev (Risk):  " << std::scientific << std::setprecision(6)
              << op.std_dev << std::endl;
    std::cout << std::endl;
}

/*
 * compute_allocation — converts optimal weights into whole-share counts.
 *
 * For each stock: target_dollars = w_i * capital, shares = floor(target / price).
 * Rounding remainders accumulate back as additional cash reserve.
 *
 * @param labels          stock ticker labels
 * @param weights         optimal weight vector (sums to 1.0)
 * @param current_prices  latest price per stock
 * @param capital         investable capital in dollars (e.g. 90000.0)
 * @return                vector of Allocation structs, one per stock
 */
std::vector<Allocation> compute_allocation(
    const std::vector<std::string>& labels,
    const std::vector<double>& weights,
    const std::vector<double>& current_prices,
    double capital) {
    std::vector<Allocation> allocations;
    allocations.reserve(labels.size());

    for (size_t i = 0; i < labels.size(); ++i) {
        Allocation a;
        a.ticker = labels[i];
        a.weight = weights[i];
        a.current_price = current_prices[i];
        // Dollar amount this stock should receive based on its weight
        a.target_dollars = weights[i] * capital;
        // Round down to whole shares — no fractional shares allowed
        a.shares = (int)std::floor(a.target_dollars / current_prices[i]);
        // Actual dollars deployed into this stock
        a.invested = a.shares * current_prices[i];
        // Leftover from rounding — returns to the cash reserve
        a.remainder = a.target_dollars - a.invested;
        allocations.push_back(a);
    }

    return allocations;
}

/*
 * print_allocation — prints the share allocation table and totals.
 *
 * Shows per-stock weight, price, target dollars, share count, invested
 * amount, and rounding remainder, followed by aggregate totals.
 *
 * @param labels      stock ticker labels
 * @param allocation  vector of Allocation structs (one per stock)
 * @param capital     total investable capital (for header display)
 */
void print_allocation(const std::vector<std::string>& labels,
                      const std::vector<Allocation>& allocation,
                      double capital) {
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "=== Portfolio Allocation ($"
              << capital << ") ===" << std::endl;

    double total_invested = 0.0;
    double total_remainder = 0.0;

    for (const auto& a : allocation) {
        std::cout << "  " << a.ticker << ": "
                  << "w=" << std::fixed << std::setprecision(4) << a.weight
                  << "  price=$" << std::fixed << std::setprecision(2) << a.current_price
                  << "  target=$" << std::fixed << std::setprecision(2) << a.target_dollars
                  << "  shares=" << a.shares
                  << "  invested=$" << std::fixed << std::setprecision(2) << a.invested
                  << "  remainder=$" << std::fixed << std::setprecision(2) << a.remainder
                  << std::endl;
        total_invested += a.invested;
        total_remainder += a.remainder;
    }

    std::cout << "  ---" << std::endl;
    std::cout << "  Total Invested:  $" << std::fixed << std::setprecision(2)
              << total_invested << std::endl;
    std::cout << "  Total Remainder: $" << std::fixed << std::setprecision(2)
              << total_remainder
              << "  (rounding cash returned to reserve)" << std::endl;
    std::cout << std::endl;
}

/*
 * load_holdings — reads current portfolio positions from a CSV file.
 *
 * If the file doesn't exist (first run), returns a vector of Holding
 * structs with 0 shares for every ticker. Otherwise parses CSV rows
 * (header: ticker,shares,avg_price,last_updated) into a map keyed by
 * ticker, then builds the result vector in label order.
 *
 * @param filepath  path to the holdings CSV file
 * @param labels    stock ticker labels in portfolio order
 * @return          vector of Holding structs, one per label
 */
std::vector<Holding> load_holdings(const std::string& filepath,
                                   const std::vector<std::string>& labels) {
    std::vector<Holding> holdings;

    // Build a map from ticker -> parsed holding data
    std::map<std::string, Holding> holdings_map;

    std::ifstream file(filepath);
    if (file.is_open()) {
        std::string line;
        // Skip header line
        std::getline(file, line);

        // Parse each row: ticker,shares,avg_price,last_updated
        while (std::getline(file, line)) {
            if (line.empty()) continue;

            std::istringstream ss(line);
            std::string token;
            Holding h;

            // field 1: ticker
            std::getline(ss, h.ticker, ',');
            // field 2: shares
            std::getline(ss, token, ',');
            h.shares = std::stoi(token);
            // field 3: avg_price
            std::getline(ss, token, ',');
            h.avg_price = std::stod(token);
            // field 4: last_updated
            std::getline(ss, h.last_updated, ',');

            holdings_map[h.ticker] = h;
        }
        file.close();
    }

    // Build result vector in label order; default to 0 shares if not found
    for (const auto& label : labels) {
        if (holdings_map.count(label)) {
            holdings.push_back(holdings_map[label]);
        } else {
            // First run or new stock — initialize with 0 shares
            Holding h;
            h.ticker = label;
            h.shares = 0;
            h.avg_price = 0.0;
            h.last_updated = "N/A";
            holdings.push_back(h);
        }
    }

    return holdings;
}

/*
 * compute_trades — computes per-stock trade deltas with cash floor enforcement.
 *
 * Three-pass approach:
 *   1. Compute raw deltas: delta = target_shares - current_shares
 *   2. Execute sells first (delta < 0) — always in full; freed cash is
 *      added to available_cash
 *   3. Execute buys (delta > 0) in array order — each buy is checked
 *      against the cash floor:
 *        max_spendable = available_cash - cash_floor
 *        If the full buy fits, execute it; otherwise reduce to
 *        floor(max_spendable / price) shares. If nothing is affordable,
 *        force HOLD and print a warning.
 *
 * @param labels              stock ticker labels in portfolio order
 * @param allocation          target allocation from the optimizer
 * @param holdings            current portfolio positions
 * @param total_capital       total fund size (e.g. $100,000)
 * @param floor_pct           minimum cash reserve as a fraction (e.g. 0.05 = 5%)
 * @param available_cash_out  output: post-trade cash balance after all trades
 * @return                    vector of Trade structs, one per stock
 */
std::vector<Trade> compute_trades(
    const std::vector<std::string>& labels,
    const std::vector<Allocation>& allocation,
    const std::vector<Holding>& holdings,
    double total_capital,
    double floor_pct,
    double& available_cash_out) {

    double cash_floor = floor_pct * total_capital;
    size_t n = labels.size();

    // Compute available cash = total_capital - current holdings value
    double available_cash = total_capital;
    for (size_t i = 0; i < n; ++i) {
        available_cash -= holdings[i].shares * allocation[i].current_price;
    }

    // Initialize trades with raw deltas
    std::vector<Trade> trades(n);
    for (size_t i = 0; i < n; ++i) {
        trades[i].ticker = labels[i];
        trades[i].current_shares = holdings[i].shares;
        trades[i].target_shares = allocation[i].shares;
        trades[i].delta = allocation[i].shares - holdings[i].shares;
        trades[i].current_price = allocation[i].current_price;
        trades[i].cost = 0.0;
        trades[i].action = "HOLD";
    }

    // Pass 1: Execute all sells first (delta < 0) — frees cash for buys.
    for (size_t i = 0; i < n; ++i) {
        if (trades[i].delta < 0) {
            trades[i].action = "SELL";
            trades[i].cost = trades[i].delta * trades[i].current_price;  // negative cost = proceeds
            available_cash -= trades[i].cost;  // subtracting negative = adding proceeds
        }
    }

    // Pass 2: Execute buys (delta > 0), enforcing cash floor.
    for (size_t i = 0; i < n; ++i) {
        if (trades[i].delta > 0) {
            double trade_value = trades[i].delta * trades[i].current_price;

            double max_spendable = available_cash - cash_floor;
            double full_cost = trade_value;

            if (full_cost <= max_spendable) {
                // Full buy fits within cash floor constraint
                trades[i].action = "BUY";
                trades[i].cost = full_cost;
                available_cash -= full_cost;
            } else if (max_spendable > trades[i].current_price) {
                // Partial buy — reduce to what we can afford
                int affordable_shares = (int)std::floor(max_spendable / trades[i].current_price);
                if (affordable_shares > 0) {
                    trades[i].action = "BUY";
                    trades[i].delta = affordable_shares;
                    trades[i].target_shares = trades[i].current_shares + affordable_shares;
                    trades[i].cost = affordable_shares * trades[i].current_price;
                    available_cash -= trades[i].cost;
                    std::cout << "  WARNING: " << trades[i].ticker
                              << " buy reduced from " << (allocation[i].shares - holdings[i].shares)
                              << " to " << affordable_shares
                              << " shares (cash floor constraint)" << std::endl;
                } else {
                    // Can't afford even one share
                    trades[i].action = "HOLD";
                    trades[i].delta = 0;
                    trades[i].target_shares = trades[i].current_shares;
                    std::cout << "  WARNING: " << trades[i].ticker
                              << " buy skipped — insufficient cash above floor" << std::endl;
                }
            } else {
                // Can't afford even one share
                trades[i].action = "HOLD";
                trades[i].delta = 0;
                trades[i].target_shares = trades[i].current_shares;
                std::cout << "  WARNING: " << trades[i].ticker
                          << " buy skipped — insufficient cash above floor" << std::endl;
            }
        }
    }

    // Export final available cash so callers don't need to recompute
    available_cash_out = available_cash;

    return trades;
}

/*
 * print_trades — prints the trade plan with per-stock details and totals.
 *
 * Shows each stock's current holdings, target, delta, action, and cost.
 * Then prints aggregate buy cost, sell proceeds, post-trade cash balance,
 * cash floor, and whether the floor constraint is satisfied.
 *
 * @param trades          vector of Trade structs (one per stock)
 * @param available_cash  cash remaining after all trades
 * @param cash_floor      minimum cash reserve requirement
 */
void print_trades(const std::vector<Trade>& trades,
                  double available_cash, double cash_floor) {
    std::cout << "=== Trade Plan ===" << std::endl;

    double total_buy_cost = 0.0;
    double total_sell_proceeds = 0.0;

    for (const auto& t : trades) {
        // Format delta with explicit sign for clarity
        std::string delta_str;
        if (t.delta > 0) delta_str = "+" + std::to_string(t.delta);
        else if (t.delta < 0) delta_str = std::to_string(t.delta);
        else delta_str = "0";

        std::cout << "  " << t.ticker << ": "
                  << "hold=" << t.current_shares
                  << "  target=" << t.target_shares
                  << "  delta=" << delta_str
                  << "  action=" << t.action
                  << "  cost=$" << std::fixed << std::setprecision(2)
                  << t.cost << std::endl;

        // Accumulate buy costs and sell proceeds separately
        if (t.cost > 0) total_buy_cost += t.cost;
        if (t.cost < 0) total_sell_proceeds += t.cost;  // negative value
    }

    std::cout << "  ---" << std::endl;
    std::cout << "  Total Buy Cost:     $" << std::fixed << std::setprecision(2)
              << total_buy_cost << std::endl;
    std::cout << "  Total Sell Proceeds: $" << std::fixed << std::setprecision(2)
              << -total_sell_proceeds << std::endl;
    std::cout << "  Cash After Trades:  $" << std::fixed << std::setprecision(2)
              << available_cash << std::endl;
    std::cout << "  Cash Floor:         $" << std::fixed << std::setprecision(2)
              << cash_floor << std::endl;
    std::cout << "  Status: "
              << (available_cash >= cash_floor ? "OK" : "WARNING — below cash floor!")
              << std::endl;
    std::cout << std::endl;
}

/*
 * save_holdings — writes updated portfolio positions to a CSV file.
 *
 * Overwrites the file with a header row followed by one row per stock.
 * Each row contains the post-trade share count (current + delta),
 * the current price, and a timestamp of when the file was written.
 *
 * @param filepath  path to the holdings CSV file
 * @param trades    vector of Trade structs with computed deltas
 */
void save_holdings(const std::string& filepath,
                   const std::vector<Trade>& trades) {
    std::ofstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "Error: could not write to " << filepath << std::endl;
        return;
    }

    // Get current system time for the last_updated field
    std::time_t now = std::time(nullptr);
    std::tm now_tm = {};
#ifdef _WIN32
    localtime_s(&now_tm, &now);
#else
    localtime_r(&now, &now_tm);
#endif
    char time_buf[64];
    std::snprintf(time_buf, sizeof(time_buf), "%04d-%02d-%02d %02d:%02d:%02d",
                  now_tm.tm_year + 1900, now_tm.tm_mon + 1, now_tm.tm_mday,
                  now_tm.tm_hour, now_tm.tm_min, now_tm.tm_sec);

    // Write CSV header
    file << "ticker,shares,avg_price,last_updated" << std::endl;

    // Write one row per stock with updated position
    for (const auto& t : trades) {
        int updated_shares = t.current_shares + t.delta;
        file << t.ticker << ","
             << updated_shares << ","
             << std::fixed << std::setprecision(2) << t.current_price << ","
             << time_buf << std::endl;
    }

    file.close();
    std::cout << "Holdings saved to " << filepath << std::endl;
}

/*
 * write_trades_csv — writes executed trades (BUY/SELL only) to a CSV file.
 *
 * Skips HOLD entries (trades that fell below the threshold) so the output
 * contains only actionable trades. Appends a CASH_RESERVE summary row
 * showing the post-trade cash balance.
 *
 * CSV columns:
 *   ticker          — stock symbol (or "CASH_RESERVE" for summary)
 *   action          — "buy" or "sell" (lowercase), or "summary"
 *   amount_of_shares — abs(delta) for trades, 0 for summary
 *   total_change    — dollar value of the trade (negative for sells)
 *
 * @param filepath          output file path (e.g. "trades.csv")
 * @param trades            vector of Trade structs from compute_trades
 * @param cash_after_trades remaining cash balance after all trades
 */
void write_trades_csv(const std::string& filepath,
                      const std::vector<Trade>& trades,
                      double cash_after_trades) {
    std::ofstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "ERROR: Could not open " << filepath << " for writing" << std::endl;
        return;
    }

    // CSV header
    file << "ticker,action,amount_of_shares,total_change" << std::endl;

    // Write one row per stock — action column shows "buy", "sell", or "hold"
    for (const auto& t : trades) {
        // Lowercase action for output consistency
        std::string action_lower;
        if (t.action == "BUY") action_lower = "buy";
        else if (t.action == "SELL") action_lower = "sell";
        else action_lower = "hold";

        // amount_of_shares is always positive (absolute delta)
        int abs_shares = std::abs(t.delta);

        // total_change: positive for buys, negative for sells
        double total_change = (t.action == "SELL")
            ? -(abs_shares * t.current_price)
            :  (abs_shares * t.current_price);

        file << t.ticker << ","
             << action_lower << ","
             << abs_shares << ","
             << std::fixed << std::setprecision(2) << total_change << std::endl;
    }

    // Summary row showing remaining cash after all trades
    file << "CASH_RESERVE,summary,0,"
         << std::fixed << std::setprecision(2) << cash_after_trades << std::endl;

    file.close();
    std::cout << "Trades written to " << filepath << std::endl;
}

/*
 * main — entry point. Accepts CLI arguments for dynamic stock selection:
 *   ./prediction.exe <data_dir> <output_dir> <TICKER1> [TICKER2] ...
 *
 * Loads per-ticker CSV files from data_dir, aligns their timestamps to a
 * common index via forward-fill, computes per-minute returns, builds the
 * covariance matrix, generates frontier portfolios, selects the optimal
 * portfolio, computes trades, and writes results to output_dir.
 */
int main(int argc, char* argv[]) {
    // Validate minimum argument count: program name + data_dir + output_dir
    // + total_capital + investable_capital + at least 1 ticker
    if (argc < 6) {
        std::cerr << "Usage: " << argv[0]
                  << " <data_dir> <output_dir> <total_capital> <investable_capital>"
                  << " <TICKER1> [TICKER2] ..." << std::endl;
        return 1;
    }

    // Parse CLI arguments
    std::string data_dir = argv[1];    // directory containing per-ticker CSV files
    std::string output_dir = argv[2];  // directory for output files (holdings.csv, portfolio.csv)
    double total_capital = std::stod(argv[3]);       // total fund size (e.g. 100000000.0)
    double investable_capital = std::stod(argv[4]);  // capital available for stock allocation (e.g. 90% of total)

    // Collect ticker symbols from remaining arguments (start at index 5)
    std::vector<std::string> labels;
    for (int i = 5; i < argc; i++) {
        labels.push_back(argv[i]);
    }

    // Load CSV data for each ticker, skipping tickers with no data
    std::vector<std::vector<StockRow>> all_stocks;
    std::vector<std::string> valid_labels;
    for (const auto& ticker : labels) {
        std::string csv_path = data_dir + "/" + ticker + ".csv";
        std::vector<StockRow> rows = load_csv(csv_path);
        if (rows.empty()) {
            std::cerr << "Warning: No data loaded for " << ticker
                      << " (file: " << csv_path << "), skipping." << std::endl;
            continue;
        }
        all_stocks.push_back(std::move(rows));
        valid_labels.push_back(ticker);
    }

    // Exit if no stocks had valid data
    if (all_stocks.empty()) {
        std::cerr << "Error: No valid stock data loaded. Exiting." << std::endl;
        return 1;
    }

    // Use valid_labels going forward (tickers that actually had data)
    labels = valid_labels;

    // Print raw loaded data before alignment modifies the vectors
    std::cout << "=== Stock Data Summary ===" << std::endl << std::endl;
    for (size_t i = 0; i < all_stocks.size(); i++) {
        print_summary(all_stocks[i]);
    }

    // Build pointer vector for align_timestamps (expects vector of pointers)
    std::vector<std::vector<StockRow>*> stock_ptrs;
    for (auto& stock : all_stocks) {
        stock_ptrs.push_back(&stock);
    }

    // Align all stocks to a common set of timestamps.
    // Stocks with missing timestamps are forward-filled from their last known row.
    std::vector<size_t> original_sizes;
    align_timestamps(stock_ptrs, original_sizes);

    // Print alignment summary showing how many rows were filled per stock
    std::vector<size_t> aligned_sizes;
    for (const auto& stock : all_stocks) {
        aligned_sizes.push_back(stock.size());
    }
    print_alignment_summary(labels, original_sizes, aligned_sizes);

    // Compute per-minute returns for each aligned stock series.
    // r_t = (price_t - price_{t-1}) / price_{t-1}
    // First element is 0.0 (no prior price), so vectors stay index-aligned.
    std::vector<std::vector<double>> all_returns;
    std::cout << "=== Returns Summary ===" << std::endl;
    for (size_t i = 0; i < all_stocks.size(); i++) {
        std::vector<double> returns = compute_returns(all_stocks[i]);
        print_returns_summary(labels[i], returns);
        all_returns.push_back(std::move(returns));
    }
    std::cout << std::endl;

    // Compute mean return per stock (skip index 0 which is always 0.0)
    std::vector<double> mean_returns = compute_mean_returns(all_returns);

    // Build NxN sample covariance matrix with Bessel's correction
    std::vector<std::vector<double>> cov_matrix =
        compute_covariance_matrix(all_returns, mean_returns);

    print_covariance_summary(labels, mean_returns, cov_matrix);

    // Generate ~1000 random portfolios on the efficient frontier.
    // Each portfolio has random long-only weights summing to 1.0,
    // with computed expected return and risk (std dev).
    std::vector<Portfolio> frontier =
        generate_frontier_portfolios(mean_returns, cov_matrix, 1000);
    print_frontier_summary(labels, frontier);

    // Find the optimal portfolio (highest Sharpe ratio, r_f = 0.0)
    size_t optimal_idx = find_optimal_portfolio(frontier, 0.0);
    print_optimal_portfolio(labels, frontier, optimal_idx);

    // Gather current prices from the last aligned row of each stock
    std::vector<double> current_prices;
    for (const auto& stock : all_stocks) {
        current_prices.push_back(stock.back().current_price);
    }

    // Compute share allocation: floor(w_i * investable_capital / price_i) per stock
    // Rounding remainders accumulate back into the cash reserve
    std::vector<Allocation> allocation = compute_allocation(
        labels, frontier[optimal_idx].weights, current_prices, investable_capital);
    print_allocation(labels, allocation, investable_capital);

    // Compare target vs current allocation and compute trades
    double cash_floor_pct = 0.05;        // 5% minimum cash reserve
    double cash_floor = cash_floor_pct * total_capital;  // $5,000,000

    // Load current holdings from CSV (0 shares on first run if file absent)
    // Holdings file lives in the output directory
    std::string holdings_file = output_dir + "/holdings.csv";
    std::vector<Holding> holdings = load_holdings(holdings_file, labels);

    // Compute trade deltas with 5% cash floor enforcement
    // Sells execute first to free cash, then buys are checked against floor
    double available_cash = 0.0;
    std::vector<Trade> trades = compute_trades(
        labels, allocation, holdings, total_capital, cash_floor_pct,
        available_cash);

    // Print trade plan and save updated positions
    print_trades(trades, available_cash, cash_floor);
    save_holdings(holdings_file, trades);

    // Write all trades (buy/sell/hold) to portfolio.csv in the output directory
    write_trades_csv(output_dir + "/portfolio.csv", trades, available_cash);

    return 0;
}
