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
#include <map>
#include <set>

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
              [](StockRow& a, StockRow& b) {
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
                std::tm* new_tm = std::localtime(&t);
                filled.timestamp = *new_tm;
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
 * main — entry point. Loads all three test CSV files, aligns their
 * timestamps to a common index via forward-fill, and prints summaries.
 */
int main() {
    // paths are relative to the prediction/ directory
    std::vector<StockRow> aapl = load_csv("test_data/AAPL.csv");
    std::vector<StockRow> bobs = load_csv("test_data/BOBS.csv");
    std::vector<StockRow> msft = load_csv("test_data/MSFT.csv");

    // Align all three stocks to a common set of timestamps.
    // Stocks with missing timestamps (e.g. BOBS has gaps from low liquidity)
    // are forward-filled from their last known row.
    std::vector<size_t> original_sizes;
    align_timestamps({&aapl, &bobs, &msft}, original_sizes);

    // Print alignment summary showing how many rows were filled per stock
    std::vector<std::string> labels = {"AAPL", "BOBS", "MSFT"};
    std::vector<size_t> aligned_sizes = {aapl.size(), bobs.size(), msft.size()};
    print_alignment_summary(labels, original_sizes, aligned_sizes);

    std::cout << "=== Stock Data Summary ===" << std::endl << std::endl;

    print_summary(aapl);
    print_summary(bobs);
    print_summary(msft);

    return 0;
}
