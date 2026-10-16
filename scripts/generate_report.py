"""
scripts/generate_report.py — Report Generator.
Generates JSON and HTML summaries adhering to contracts/verification_schemas.py format.
"""

import os
import sys

# Add repository root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from contracts.verification_schemas import VerificationReport


def generate_html_report(report: VerificationReport, output_path: str):
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ROCmigrator Verification Report - {report.job_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #0f172a; color: #f8fafc; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 24px; margin-bottom: 20px; border: 1px solid #334155; }}
        .badge-verified {{ background: #10b981; color: white; padding: 4px 12px; border-radius: 9999px; font-weight: bold; }}
        .badge-failed {{ background: #ef4444; color: white; padding: 4px 12px; border-radius: 9999px; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #0f172a; }}
    </style>
</head>
<body>
    <h1>ROCmigrator Numerical Verification Report</h1>
    <div class="card">
        <h2>Job: {report.job_id}</h2>
        <p>Status: <span class="{'badge-verified' if report.overall_status == 'VERIFIED' else 'badge-failed'}">{report.overall_status}</span></p>
        <p>CPU Reference Verified: <strong>{'Yes' if report.cpu_reference_verified else 'No'}</strong></p>
        <p>Determinism Test: <strong>{'Passed' if report.determinism_passed else 'Failed'}</strong></p>
        <p>Summary: {report.summary}</p>
        <p>Total Tests: {report.total_tests} | Passed: {report.passed_tests} | Failed: {report.failed_tests}</p>
    </div>

    <div class="card">
        <h3>Test Details</h3>
        <table>
            <thead>
                <tr>
                    <th>Seed</th>
                    <th>Shape</th>
                    <th>Dtype</th>
                    <th>Max Abs Err</th>
                    <th>Max Rel Err</th>
                    <th>NaN/Inf</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""
    for res in report.results:
        html_content += f"""
                <tr>
                    <td>{res.seed}</td>
                    <td>{list(res.shape)}</td>
                    <td>{res.dtype}</td>
                    <td>{res.max_abs_err:.2e}</td>
                    <td>{res.max_rel_err:.2e}</td>
                    <td>{'Yes' if res.nan_inf_detected else 'No'}</td>
                    <td><span class="{'badge-verified' if res.passed else 'badge-failed'}">{'PASSED' if res.passed else 'FAILED'}</span></td>
                </tr>
"""
    html_content += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def main():
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
    else:
        json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "golden-repo-01", "verification_report.json"))

    if not os.path.exists(json_path):
        print(f"Error: JSON report not found: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        report = VerificationReport.model_validate_json(f.read())
    html_out = os.path.splitext(json_path)[0] + ".html"
    generate_html_report(report, html_out)
    print(f"HTML report successfully generated: {html_out}")


if __name__ == "__main__":
    main()
