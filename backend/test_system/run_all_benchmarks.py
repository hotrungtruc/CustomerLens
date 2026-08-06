import os
import sys
import argparse
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from test_system.benchmark_accuracy import evaluate_accuracy
from test_system.benchmark_speed import benchmark_speed
from test_system.benchmark_e2e_stress import benchmark_e2e_stress
from test_system.generate_report import generate_markdown_report

def main():
    parser = argparse.ArgumentParser(description="AI System Accuracy and Speed Benchmark Runner")
    parser.add_argument(
        "--num-identities",
        type=int,
        default=300,
        help="Number of random identities from asian_celeb dataset to benchmark (default: 300)"
    )
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default=r"C:\SCHOOL\asian_celeb_112x112_folders",
        help="Path to asian_celeb_112x112_folders dataset directory"
    )
    parser.add_argument(
        "--speed-runs",
        type=int,
        default=200,
        help="Number of iterations for ONNX inference speed benchmark (default: 200)"
    )
    parser.add_argument(
        "--skip-accuracy",
        action="store_true",
        help="Skip accuracy benchmark phase"
    )
    parser.add_argument(
        "--skip-speed",
        action="store_true",
        help="Skip speed benchmark phase"
    )
    parser.add_argument(
        "--skip-stress",
        action="store_true",
        help="Skip e2e stress benchmark phase"
    )

    args = parser.parse_args()

    results_dir = os.path.join(backend_dir, "test_system", "results")
    os.makedirs(results_dir, exist_ok=True)

    print("=" * 80)
    print("  === STARTING AI BENCHMARK SUITE FOR FACE RECOGNITION SYSTEM ===")
    print(f"  - Target Dataset      : {args.dataset_dir}")
    print(f"  - Sampled Identities  : {args.num_identities} random people")
    print(f"  - Output Directory    : {results_dir}")
    print("=" * 80)

    # 1. Run Accuracy Benchmark
    if not args.skip_accuracy:
        acc_output = os.path.join(results_dir, "accuracy_results.json")
        evaluate_accuracy(
            dataset_dir=args.dataset_dir,
            num_identities=args.num_identities,
            output_json=acc_output
        )
    else:
        print("\n[Skipped] Accuracy benchmark phase.")

    # 2. Run Speed Benchmark
    if not args.skip_speed:
        speed_output = os.path.join(results_dir, "speed_results.json")
        benchmark_speed(
            num_runs=args.speed_runs,
            output_json=speed_output
        )
    else:
        print("\n[Skipped] Speed benchmark phase.")

    # 3. Run E2E Stress Benchmark
    if not args.skip_stress:
        stress_output = os.path.join(results_dir, "e2e_stress_results.json")
        benchmark_e2e_stress(
            camera_counts=[1, 2, 4],
            test_duration_per_level=5.0,
            output_json=stress_output
        )
    else:
        print("\n[Skipped] E2E stress benchmark phase.")

    # 4. Generate Comprehensive Markdown Report
    print("\n" + "=" * 80)
    print("  [REPORT] GENERATING ACADEMIC MARKDOWN REPORT")
    print("=" * 80)
    report_file = os.path.join(backend_dir, "test_system", "benchmark_report.md")
    generate_markdown_report(output_file=report_file)

    print("\n[SUCCESS] BENCHMARK COMPLETE!")
    print(f"   View Report: {report_file}")

if __name__ == "__main__":
    main()
