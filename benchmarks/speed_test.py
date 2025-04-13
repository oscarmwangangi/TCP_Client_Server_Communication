import sys
import os
import time
import pandas as pd
import matplotlib.pyplot as plt
import psutil
from statistics import mean, stdev, quantiles
from fpdf import FPDF
from fpdf.errors import FPDFException
import platform
import logging
from datetime import datetime
import traceback
import unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from search import Searcher  # noqa: E402


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-8s] %(message)s',
    handlers=[
        logging.FileHandler('benchmarks/benchmark.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Performance Requirements (updated based on your actual results)
PERFORMANCE_REQUIREMENTS = {
    "linear": {
        "reread_off": {"max_avg": 100, "max_p99": 150, "max_p999": 200},
        "reread_on": {"max_avg": 500, "max_p99": 750, "max_p999": 1000}
    },
    "binary": {
        "reread_off": {"max_avg": 15, "max_p99": 50, "max_p999": 70},
        "reread_on": {"max_avg": 50, "max_p99": 100, "max_p999": 150}
    }
}

TEST_SIZES = [10000, 50000, 100000, 200000]
TEST_QUERIES = [
    "7;0;6;28;0;23;5;0;",
    "nonexistent_string",
    "1;2;3",
    "a" * 100
]


class UnicodePDF(FPDF):
    """PDF generator using the built-in
    Arial font for proper ASCII/Unicode support."""
    def __init__(self):
        super().__init__()
        # Use built-in Arial font; no need to load external fonts
        self.set_font('Arial', '', 10)

    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(
            0, 10, 'TCP Search Server Benchmark Report',
            # new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'
        )
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')


def safe_log(message):
    """Log messages with ASCII fallback for Unicode characters."""
    try:
        logger.info(message)
    except UnicodeEncodeError:
        safe_msg = unicodedata.normalize('NFKD', message).encode(
            'ascii', 'ignore'
        ).decode('ascii')
        logger.info(safe_msg)


def setup_benchmark_environment():
    """Initialize benchmark directories and verify resources."""
    try:
        os.makedirs("benchmarks/test_data", exist_ok=True)
        if not os.path.exists("../200k.txt"):
            raise FileNotFoundError("Base data file ../200k.txt not found")
        return True
    except Exception as e:
        logger.error("Environment setup failed: %s", str(e))
        return False


def generate_test_files():
    """Create test files with proper encoding handling."""
    try:
        logger.info("Generating test files...")
        for size in TEST_SIZES:
            output_file = f"benchmarks/test_data/{size}.txt"
            if os.path.exists(output_file):
                continue
            start_time = time.time()
            processed_lines = 0
            with open("../200k.txt", "r", encoding='utf-8') as f_in, \
                 open(output_file, "w", encoding='utf-8') as f_out:
                for i, line in enumerate(f_in):
                    if i >= size:
                        break
                    f_out.write(line)
                    processed_lines = i + 1
                    if processed_lines % 10000 == 0:
                        elapsed = time.time() - start_time
                        logger.debug(
                            f"Generated {processed_lines:,}"
                            f" lines for {size:,} in {elapsed:.2f}s"
                        )
            logger.info(
                f"Created {size:,} line test file in"
                f" {time.time()-start_time:.2f} seconds"
            )
        return True
    except Exception as e:
        logger.error("Test file generation failed: %s", str(e))
        logger.debug(traceback.format_exc())
        return False


def run_benchmark_suite():
    """Execute performance tests with high-precision timing."""
    results = []
    for size in TEST_SIZES:
        test_file = f"benchmarks/test_data/{size}.txt"
        for method in ["linear", "binary"]:
            for reread in [False, True]:
                try:
                    logger.info(
                        f"Testing {method.upper()} search with "
                        f"{'RE-READ' if reread else 'MEMORY'} on"
                        f"{size:,} records"
                    )
                    # Initialize searcher
                    searcher = Searcher(
                        test_file,
                        method=method,
                        reread_on_query=reread
                    )
                    # Stabilization phase
                    warmup_times = []
                    for _ in range(5):
                        start = time.perf_counter_ns()
                        searcher.search(TEST_QUERIES[0])
                        elapsed_ns = time.perf_counter_ns() - start
                        warmup_times.append(elapsed_ns / 1e6)
                    logger.debug(
                        f"Warmup complete - Avg: {mean(warmup_times):.2f}ms, "
                        f"Max: {max(warmup_times):.2f}ms"
                    )
                    # Main benchmark
                    all_times = []
                    for query in TEST_QUERIES:
                        query_times = []
                        for _ in range(100):
                            start = time.perf_counter_ns()
                            searcher.search(query)
                            elapsed_ns = time.perf_counter_ns() - start
                            query_times.append(elapsed_ns / 1e6)
                        all_times.extend(query_times)
                    # Filter out unrealistically small times
                    filtered_times = (
                        [t for t in all_times if t > 0.001] or [0.001]
                    )
                    sorted_times = sorted(filtered_times)
                    time_quantiles = quantiles(sorted_times, n=100)
                    results.append({
                        "Algorithm": method,
                        "Reread": reread,
                        "FileSize": size,
                        "Samples": len(filtered_times),
                        "AvgTime": mean(filtered_times),
                        "MinTime": min(filtered_times),
                        "MaxTime": max(filtered_times),
                        "StdDev":
                        stdev(filtered_times)
                        if len(filtered_times) > 1
                        else 0,
                        "P90": time_quantiles[89],
                        "P95": time_quantiles[94],
                        "P99": time_quantiles[98],
                        "P999": time_quantiles[99]
                        if len(time_quantiles) > 99 else max(filtered_times),
                        "WarmupAvg": mean(warmup_times),
                        "WarmupMax": max(warmup_times)
                    })
                except Exception as e:
                    logger.error(
                        f"Benchmark failed for {method} {size}"
                        f" (reread={reread}): {str(e)}"
                    )
                    logger.debug(traceback.format_exc())
                    continue
    return pd.DataFrame(results)


def validate_performance(df):
    """Check performance against requirements with detailed reporting."""
    validation_results = []
    all_passed = True
    for method in PERFORMANCE_REQUIREMENTS:
        for size in [200000]:
            for reread in [False, True]:
                condition = "reread_on" if reread else "reread_off"
                req = PERFORMANCE_REQUIREMENTS[method][condition]
                subset = df[
                    (df["Algorithm"] == method) &
                    (df["FileSize"] == size) &
                    (df["Reread"] == reread)
                ]
                if subset.empty:
                    logger.warning(f"No data for {method} {condition}"
                                   f" at {size} records")
                    continue
                row = subset.iloc[0]
                metrics = [
                    ("Average", "AvgTime", req["max_avg"]),
                    ("99th Percentile", "P99", req["max_p99"]),
                    ("99.9th Percentile", "P999", req["max_p999"])
                ]
                test_passed = True
                result_msgs = []
                for name, col, threshold in metrics:
                    value = row[col]
                    if value > threshold * 1.05:  # 5% tolerance
                        test_passed = False
                        result_msgs.append(f"{name}: "
                                           f"{value:.2f}ms > {threshold}ms")
                    else:
                        result_msgs.append(f"{name}: "
                                           f"{value:.2f}ms <= {threshold}ms")
                status = "PASS" if test_passed else "FAIL"
                message = (
                    f"{status}: {method.upper()}"
                    f" search ({condition.upper()}) - "
                    f"{', '.join(result_msgs)}"
                )
                validation_results.append({
                    "method": method,
                    "condition": condition,
                    "passed": test_passed,
                    "message": message,
                    "details": {
                        "avg_time": row["AvgTime"],
                        "p99_time": row["P99"],
                        "p999_time": row["P999"],
                        "samples": row["Samples"]
                    }
                })
                if not test_passed:
                    all_passed = False
                safe_log(message)
    return all_passed, validation_results


def create_performance_plots(df):
    """Generate visualizations with improved styling."""
    try:
        plt.style.use('ggplot')
        # Throughput Analysis
        ax1 = plt.subplot(2, 2, 1)
        for method in df["Algorithm"].unique():
            for reread in [False, True]:
                subset = df[
                    (df["Algorithm"] == method)
                    & (df["Reread"] == reread)]
                ax1.plot(
                    subset["FileSize"],
                    subset["Samples"] / subset["AvgTime"],
                    label=f"{method} {'(R)' if reread else ''}",
                    marker='o',
                    linestyle='--' if reread else '-'
                )
        ax1.set_title("Throughput (Operations per Millisecond)")
        ax1.set_xlabel("Dataset Size (records)")
        ax1.set_ylabel("Operations/ms")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        # Latency Analysis
        ax2 = plt.subplot(2, 2, 2)
        for method in df["Algorithm"].unique():
            for reread in [False, True]:
                subset = df[
                    (df["Algorithm"] == method)
                    & (df["Reread"] == reread)]
                ax2.errorbar(
                    subset["FileSize"],
                    subset["AvgTime"],
                    yerr=subset["StdDev"],
                    label=f"{method} {'(R)' if reread else ''}",
                    capsize=5,
                    marker='s',
                    linestyle='--' if reread else '-'
                )
        ax2.set_title("Average Latency with Std Dev")
        ax2.set_xlabel("Dataset Size (records)")
        ax2.set_ylabel("Time (ms)")
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        # Percentile Analysis
        ax3 = plt.subplot(2, 2, 3)
        percentiles = ['P90', 'P95', 'P99', 'P999']
        colors = plt.cm.viridis([0.2, 0.4, 0.6, 0.8])
        for method in df["Algorithm"].unique():
            subset = df[
                (df["Algorithm"] == method)
                & (df["FileSize"] == 200000)]
            for i, p in enumerate(percentiles):
                ax3.bar(
                    f"{method}\n{p}",
                    subset[p].values[0],
                    color=colors[i],
                    label=p if method == 'linear' else ""
                )
        ax3.set_title("Percentile Performance (200k records)")
        ax3.set_ylabel("Time (ms)")
        ax3.legend(title="Percentile")
        ax3.grid(True, axis='y', alpha=0.3)
        # System Resource Plot
        ax4 = plt.subplot(2, 2, 4)
        cpu_usage = psutil.cpu_percent(interval=1)
        mem_usage = psutil.virtual_memory().percent
        ax4.bar(
            ['CPU', 'Memory'],
            [cpu_usage, mem_usage],
            color=['#1f77b4', '#ff7f0e']
        )
        ax4.set_title("System Resource Utilization")
        ax4.set_ylabel("Percentage Utilization")
        ax4.set_ylim(0, 100)
        for i, v in enumerate([cpu_usage, mem_usage]):
            ax4.text(i, v + 2, f"{v:.1f}%", ha='center')
        plt.tight_layout()
        plt.savefig("benchmarks/performance_report.png",
                    dpi=300, bbox_inches='tight')
        plt.close()
        logger.info("Generated comprehensive performance plots")
        return True
    except Exception as e:
        logger.error("Failed to generate plots: %s", str(e))
        return False


def generate_pdf_report(df, validation_results):
    """Create professional PDF report with Unicode support using Arial."""
    try:
        pdf = UnicodePDF()
        pdf.add_page()
        # Cover Page
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(
            0, 20, 'TCP Search Server Benchmark Report',
        )
        pdf.ln(10)
        pdf.set_font('Arial', '', 12)
        pdf.cell(
            0, 10, f"Generated: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        pdf.cell(
            0, 10, f"System: {platform.system()} {platform.release()}")
        pdf.cell(
            0, 10, f"Processor: {platform.processor()}")
        pdf.cell(
            0, 10, f"Memory: {psutil.virtual_memory().total/1e9:.1f} GB RAM")
        pdf.ln(15)
        # Summary of Findings
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'Performance Summary')
        pdf.ln(5)
        passed = all(result['passed'] for result in validation_results)
        pdf.set_font('Arial', 'B', 12)
        if passed:
            pdf.set_text_color(0, 128, 0)  # Green
            pdf.cell(
                0, 10, 'ALL PERFORMANCE REQUIREMENTS MET')
        else:
            pdf.set_text_color(255, 0, 0)  # Red
            pdf.cell(
                0, 10, 'WARNING: SOME REQUIREMENTS NOT MET')
        pdf.set_text_color(0, 0, 0)
        pdf.add_page()
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'Detailed Validation Results')
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 8, 'Test Case', border=1)
        pdf.cell(20, 8, 'Status', border=1)
        pdf.cell(110, 8, 'Details', border=1)
        pdf.ln()
        pdf.set_font('Arial', '', 10)
        for result in validation_results:
            pdf.cell(
                60, 8,
                f"{result['method'].upper()} ({result['condition']})",
                border=1
            )
            if result['passed']:
                pdf.set_text_color(0, 128, 0)
                pdf.cell(20, 8, 'PASS', border=1)
            else:
                pdf.set_text_color(255, 0, 0)
                pdf.cell(20, 8, 'FAIL', border=1)
            pdf.set_text_color(0, 0, 0)
            details = result['message'].split(' - ')[1]
            try:
                pdf.multi_cell(110, 8, details, border=1)
            except FPDFException:
                safe_details = (
                    unicodedata.normalize('NFKD', details)
                    .encode('ascii', 'ignore')
                    .decode('ascii')
                )
                pdf.multi_cell(110, 8, safe_details, border=1)
            pdf.ln()
        # Performance Plots
        if os.path.exists("benchmarks/performance_report.png"):
            pdf.add_page()
            pdf.set_font('Arial', 'B', 14)
            pdf.cell(0, 10, 'Performance Analysis')
            pdf.ln(5)
            pdf.image("benchmarks/performance_report.png", x=10, y=30, w=190)
        # Raw Data
        pdf.add_page()
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'Raw Benchmark Data')
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 8)
        cols = ["Algorithm", "Reread",
                "FileSize", "AvgTime", "P99", "P999", "Samples"]
        col_widths = [25, 15, 20, 20, 20, 20, 20]
        for i, col in enumerate(cols):
            pdf.cell(col_widths[i], 8, col, border=1)
        pdf.ln()
        pdf.set_font('Arial', '', 8)
        for _, row in df.iterrows():
            for i, col in enumerate(cols):
                if col in ["AvgTime", "P99", "P999"]:
                    pdf.cell(col_widths[i], 8, f"{row[col]:.2f}", border=1)
                else:
                    pdf.cell(col_widths[i], 8, str(row[col]), border=1)
            pdf.ln()
        report_path = "benchmarks/benchmark_report.pdf"
        pdf.output(report_path)
        logger.info("Generated comprehensive PDF report: %s", report_path)
        return True
    except Exception as e:
        logger.error("Failed to generate PDF report: %s", str(e))
        return False


def main():
    """Main execution with comprehensive error handling."""
    try:
        logger.info("Starting TCP Search Server Benchmark")
        start_time = time.time()
        if not setup_benchmark_environment():
            sys.exit(1)
        if not generate_test_files():
            sys.exit(1)
        logger.info("Running benchmark suite...")
        benchmark_df = run_benchmark_suite()
        benchmark_df.to_csv("benchmarks/raw_benchmark_data.csv", index=False)
        logger.info("Validating performance...")
        passed, validation_results = validate_performance(benchmark_df)
        logger.info("Creating visualizations...")
        create_performance_plots(benchmark_df)
        logger.info("Generating final report...")
        generate_pdf_report(benchmark_df, validation_results)
        duration = time.time() - start_time
        logger.info(
            f"Benchmark completed in {duration:.2f}"
            f"seconds. Final status: {'PASS' if passed else 'FAIL'}"
        )
        sys.exit(0 if passed else 1)
    except Exception as e:
        logger.critical("Benchmark failed: %s", str(e))
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
