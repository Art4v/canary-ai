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
 * main — entry point. Loads all three test CSV files, aligns their
 * timestamps to a common index via forward-fill, computes per-minute
 * returns, builds the covariance matrix, generates frontier portfolios,
 * and prints summaries.
 */
int main() {
    // paths are relative to the prediction/ directory
    std::vector<StockRow> aapl = load_csv("test_data/AAPL.csv");
    std::vector<StockRow> bobs = load_csv("test_data/BOBS.csv");
    std::vector<StockRow> msft = load_csv("test_data/MSFT.csv");

    // Print raw loaded data before alignment modifies the vectors
    std::cout << "=== Stock Data Summary ===" << std::endl << std::endl;
    print_summary(aapl);
    print_summary(bobs);
    print_summary(msft);

    // Align all three stocks to a common set of timestamps.
    // Stocks with missing timestamps (e.g. BOBS has gaps from low liquidity)
    // are forward-filled from their last known row.
    std::vector<size_t> original_sizes;
    align_timestamps({&aapl, &bobs, &msft}, original_sizes);

    // Print alignment summary showing how many rows were filled per stock
    std::vector<std::string> labels = {"AAPL", "BOBS", "MSFT"};
    std::vector<size_t> aligned_sizes = {aapl.size(), bobs.size(), msft.size()};
    print_alignment_summary(labels, original_sizes, aligned_sizes);

    // Compute per-minute returns for each aligned stock series.
    // r_t = (price_t - price_{t-1}) / price_{t-1}
    // First element is 0.0 (no prior price), so vectors stay index-aligned.
    std::vector<double> aapl_returns = compute_returns(aapl);
    std::vector<double> bobs_returns = compute_returns(bobs);
    std::vector<double> msft_returns = compute_returns(msft);

    std::cout << "=== Returns Summary ===" << std::endl;
    print_returns_summary("AAPL", aapl_returns);
    print_returns_summary("BOBS", bobs_returns);
    print_returns_summary("MSFT", msft_returns);
    std::cout << std::endl;

    // Bundle return vectors for matrix computation
    std::vector<std::vector<double>> all_returns = {
        aapl_returns, bobs_returns, msft_returns
    };

    // Compute mean return per stock (skip index 0 which is always 0.0)
    std::vector<double> mean_returns = compute_mean_returns(all_returns);

    // Build 3x3 sample covariance matrix with Bessel's correction
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
    std::vector<double> current_prices = {
        aapl.back().current_price,
        bobs.back().current_price,
        msft.back().current_price
    };

    // Compute share allocation: floor(w_i * $90,000 / price_i) per stock
    // Rounding remainders accumulate back into the cash reserve
    double investable_capital = 90000.0;
    std::vector<Allocation> allocation = compute_allocation(
        labels, frontier[optimal_idx].weights, current_prices, investable_capital);
    print_allocation(labels, allocation, investable_capital);

    return 0;
}
