"""
HTML Report Generator for Backtesting Results

Generates comprehensive HTML reports with charts and statistics.
"""

from typing import List, Dict, Any
from datetime import datetime
import os
from backtesting.core.models import BacktestResult


class ReportGenerator:
    """
    Generate HTML reports for backtest results

    Features:
    - Summary statistics
    - Equity curve chart
    - Trade list
    - Performance metrics
    - Multiple strategy comparison
    """

    def __init__(self, output_dir: str = "reports"):
        """
        Initialize report generator

        Args:
            output_dir: Directory to save reports (default: 'reports')
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_single_report(self, result: BacktestResult, filename: str = None) -> str:
        """
        Generate HTML report for a single backtest

        Args:
            result: BacktestResult object
            filename: Output filename (auto-generated if None)

        Returns:
            Path to generated report
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_{result.symbol}_{timestamp}.html"

        filepath = os.path.join(self.output_dir, filename)

        html = self._generate_html(result)

        with open(filepath, 'w') as f:
            f.write(html)

        return filepath

    def generate_comparison_report(self,
                                   results: List[Dict[str, Any]],
                                   filename: str = None) -> str:
        """
        Generate HTML report comparing multiple backtests

        Args:
            results: List of dicts with 'name', 'result', 'params', 'stats'
            filename: Output filename (auto-generated if None)

        Returns:
            Path to generated report
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"backtest_comparison_{timestamp}.html"

        filepath = os.path.join(self.output_dir, filename)

        html = self._generate_comparison_html(results)

        with open(filepath, 'w') as f:
            f.write(html)

        return filepath

    def _generate_html(self, result: BacktestResult) -> str:
        """Generate HTML for single backtest result"""

        # Prepare equity curve data for chart
        equity_data = []
        for point in result.equity_curve:
            equity_data.append({
                'time': point['timestamp'].isoformat() if isinstance(point['timestamp'], datetime) else str(point['timestamp']),
                'equity': point['equity']
            })

        # Prepare trades data
        trades_html = ""
        for i, trade in enumerate(result.trades, 1):
            profit_class = "profit" if trade.is_winner else "loss"
            trades_html += f"""
            <tr class="{profit_class}">
                <td>{i}</td>
                <td>{trade.side.value}</td>
                <td>{trade.entry_time.strftime('%Y-%m-%d %H:%M:%S')}</td>
                <td>{trade.exit_time.strftime('%Y-%m-%d %H:%M:%S')}</td>
                <td>${trade.entry_price:.2f}</td>
                <td>${trade.exit_price:.2f}</td>
                <td>${trade.pnl:+.2f}</td>
                <td>{trade.pnl_pct:+.2f}%</td>
                <td>{trade.duration_minutes:.1f}m</td>
                <td>{trade.exit_reason}</td>
            </tr>
            """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Backtest Report - {result.symbol}</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #eee;
            padding-bottom: 8px;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #4CAF50;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
        .positive {{ color: #4CAF50; }}
        .negative {{ color: #f44336; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .profit {{
            background-color: #e8f5e9;
        }}
        .loss {{
            background-color: #ffebee;
        }}
        #equity-chart {{
            margin: 20px 0;
            height: 400px;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Backtest Report: {result.symbol}</h1>

        <div style="background: #e3f2fd; padding: 15px; border-radius: 6px; margin: 20px 0;">
            <strong>Period:</strong> {result.start_time.strftime('%Y-%m-%d %H:%M')} to {result.end_time.strftime('%Y-%m-%d %H:%M')}<br>
            <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>

        <h2>Performance Summary</h2>
        <div class="metrics">
            <div class="metric">
                <div class="metric-label">Total Return</div>
                <div class="metric-value {'positive' if result.total_return > 0 else 'negative'}">
                    {result.total_return:+.2f}%
                </div>
            </div>
            <div class="metric">
                <div class="metric-label">Final Capital</div>
                <div class="metric-value">${result.final_capital:,.2f}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">{result.num_trades}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{result.win_rate:.1f}%</div>
            </div>
            <div class="metric">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value">{result.profit_factor:.2f}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">{result.sharpe_ratio:.2f}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value negative">{result.max_drawdown:.2f}%</div>
            </div>
            <div class="metric">
                <div class="metric-label">Avg Win</div>
                <div class="metric-value positive">${result.avg_win:.2f}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Avg Loss</div>
                <div class="metric-value negative">${result.avg_loss:.2f}</div>
            </div>
        </div>

        <h2>Equity Curve</h2>
        <div id="equity-chart"></div>

        <h2>Trade History ({result.num_trades} trades)</h2>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Side</th>
                    <th>Entry Time</th>
                    <th>Exit Time</th>
                    <th>Entry Price</th>
                    <th>Exit Price</th>
                    <th>P&L ($)</th>
                    <th>P&L (%)</th>
                    <th>Duration</th>
                    <th>Exit Reason</th>
                </tr>
            </thead>
            <tbody>
                {trades_html if trades_html else '<tr><td colspan="10" style="text-align:center;">No trades executed</td></tr>'}
            </tbody>
        </table>

        <div class="footer">
            Generated by BitPulse Backtesting Framework
        </div>
    </div>

    <script>
        // Equity curve chart
        const equityData = {equity_data};

        const trace = {{
            x: equityData.map(d => d.time),
            y: equityData.map(d => d.equity),
            type: 'scatter',
            mode: 'lines',
            name: 'Equity',
            line: {{
                color: '#4CAF50',
                width: 2
            }},
            fill: 'tozeroy',
            fillcolor: 'rgba(76, 175, 80, 0.1)'
        }};

        const layout = {{
            title: '',
            xaxis: {{
                title: 'Time',
                gridcolor: '#e0e0e0'
            }},
            yaxis: {{
                title: 'Portfolio Value ($)',
                gridcolor: '#e0e0e0'
            }},
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            margin: {{ t: 20, r: 20, b: 50, l: 60 }}
        }};

        Plotly.newPlot('equity-chart', [trace], layout, {{responsive: true}});
    </script>
</body>
</html>
        """

        return html

    def _generate_comparison_html(self, results: List[Dict[str, Any]]) -> str:
        """Generate HTML for comparing multiple backtest results"""

        # Build comparison table
        comparison_rows = ""
        for r in results:
            result = r['result']
            stats = r['stats']
            comparison_rows += f"""
            <tr>
                <td><strong>{r['name']}</strong></td>
                <td class="{'positive' if result.total_return > 0 else 'negative'}">{result.total_return:+.2f}%</td>
                <td>{result.num_trades}</td>
                <td>{result.win_rate:.1f}%</td>
                <td>{result.profit_factor:.2f}</td>
                <td>{result.sharpe_ratio:.2f}</td>
                <td class="negative">{result.max_drawdown:.2f}%</td>
                <td>${result.avg_win:.2f}</td>
                <td>${result.avg_loss:.2f}</td>
                <td>{stats['signals_generated']}</td>
                <td>{stats['signal_acceptance_rate']*100:.1f}%</td>
            </tr>
            """

        # Prepare equity curves for chart
        equity_traces = []
        for r in results:
            result = r['result']
            times = [point['timestamp'].isoformat() if isinstance(point['timestamp'], datetime) else str(point['timestamp'])
                    for point in result.equity_curve]
            values = [point['equity'] for point in result.equity_curve]
            equity_traces.append({
                'name': r['name'],
                'times': times,
                'values': values
            })

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Backtest Comparison Report</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #2196F3;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #eee;
            padding-bottom: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }}
        th {{
            background-color: #2196F3;
            color: white;
            padding: 12px;
            text-align: left;
            position: sticky;
            top: 0;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .positive {{ color: #4CAF50; font-weight: bold; }}
        .negative {{ color: #f44336; font-weight: bold; }}
        #comparison-chart {{
            margin: 20px 0;
            height: 500px;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Strategy Comparison Report</h1>

        <div style="background: #e3f2fd; padding: 15px; border-radius: 6px; margin: 20px 0;">
            <strong>Strategies Compared:</strong> {len(results)}<br>
            <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>

        <h2>Performance Comparison</h2>
        <table>
            <thead>
                <tr>
                    <th>Strategy</th>
                    <th>Total Return</th>
                    <th>Trades</th>
                    <th>Win Rate</th>
                    <th>Profit Factor</th>
                    <th>Sharpe</th>
                    <th>Max DD</th>
                    <th>Avg Win</th>
                    <th>Avg Loss</th>
                    <th>Signals</th>
                    <th>Accept Rate</th>
                </tr>
            </thead>
            <tbody>
                {comparison_rows}
            </tbody>
        </table>

        <h2>Equity Curves Comparison</h2>
        <div id="comparison-chart"></div>

        <div class="footer">
            Generated by BitPulse Backtesting Framework
        </div>
    </div>

    <script>
        const traces = {equity_traces};
        const colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336'];

        const plotData = traces.map((trace, i) => ({{
            x: trace.times,
            y: trace.values,
            type: 'scatter',
            mode: 'lines',
            name: trace.name,
            line: {{
                color: colors[i % colors.length],
                width: 2
            }}
        }}));

        const layout = {{
            title: '',
            xaxis: {{
                title: 'Time',
                gridcolor: '#e0e0e0'
            }},
            yaxis: {{
                title: 'Portfolio Value ($)',
                gridcolor: '#e0e0e0'
            }},
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            margin: {{ t: 20, r: 20, b: 50, l: 60 }},
            hovermode: 'x unified'
        }};

        Plotly.newPlot('comparison-chart', plotData, layout, {{responsive: true}});
    </script>
</body>
</html>
        """

        return html
