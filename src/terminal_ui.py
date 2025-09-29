#!/usr/bin/env python3
"""
Terminal UI for Real-time Order Book Visualization
"""

import asyncio
import sys
import click
from datetime import datetime
from typing import List, Dict, Optional
from collections import deque
import httpx

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich import box


class OrderBookAPI:
    """API client for fetching order book data"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=5.0)

    async def get_orderbook(self, symbol: str) -> Dict:
        """Fetch current order book"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/orderbook/{symbol}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            return {"error": str(e)}
        return {}

    async def get_stats(self, symbol: str) -> Dict:
        """Fetch order book statistics"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/orderbook/{symbol}/stats")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            return {"error": str(e)}
        return {}

    async def get_recent_whales(self, symbol: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Fetch recent whale orders"""
        try:
            params = {"limit": limit}
            if symbol:
                params["symbol"] = symbol
            response = await self.client.get(f"{self.base_url}/api/v1/whales/recent", params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            return []
        return []

    async def get_market_depth(self, symbol: str) -> List[Dict]:
        """Fetch market depth data"""
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/orderbook/{symbol}/depth")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            return []
        return []

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class OrderBookUI:
    """Terminal UI for order book visualization"""

    def __init__(self, api_url: str, symbols: List[str], refresh_rate: float = 1.0):
        self.api = OrderBookAPI(api_url)
        self.symbols = symbols
        self.current_symbol_idx = 0
        self.refresh_rate = refresh_rate
        self.console = Console()
        self.running = True
        self.show_whales = True
        self.show_depth = True

        # Data storage
        self.orderbook_data = {}
        self.stats_data = {}
        self.whale_data = deque(maxlen=20)
        self.depth_data = {}
        self.last_update = datetime.now()

    @property
    def current_symbol(self) -> str:
        """Get current selected symbol"""
        return self.symbols[self.current_symbol_idx] if self.symbols else "BTC_USDT"

    def create_layout(self) -> Layout:
        """Create the terminal layout"""
        layout = Layout()

        # Main layout structure
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        # Split main area
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )

        # Split left panel
        layout["left"].split_column(
            Layout(name="orderbook", ratio=3),
            Layout(name="stats", ratio=1)
        )

        # Split right panel
        layout["right"].split_column(
            Layout(name="whales", ratio=2),
            Layout(name="depth", ratio=1)
        )

        return layout

    def create_header(self) -> Panel:
        """Create header panel"""
        header_text = Text()
        header_text.append("📊 Order Book Terminal", style="bold cyan")
        header_text.append(" | ", style="dim")
        header_text.append(f"Symbol: {self.current_symbol}", style="bold yellow")
        header_text.append(" | ", style="dim")
        header_text.append(f"Last Update: {self.last_update.strftime('%H:%M:%S')}", style="green")

        return Panel(
            Align.center(header_text),
            style="bold white on blue",
            box=box.DOUBLE
        )

    def create_orderbook_panel(self) -> Panel:
        """Create order book visualization"""
        orderbook = self.orderbook_data.get(self.current_symbol, {})

        if not orderbook or "error" in orderbook:
            return Panel(
                Align.center(Text("No order book data available", style="dim")),
                title=f"📈 Order Book - {self.current_symbol}",
                border_style="cyan"
            )

        # Create table
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Bid Volume", justify="right", style="green", width=15)
        table.add_column("Bid Price", justify="right", style="green", width=12)
        table.add_column("Price", justify="center", style="yellow", width=12)
        table.add_column("Ask Price", justify="left", style="red", width=12)
        table.add_column("Ask Volume", justify="left", style="red", width=15)

        # Get bids and asks
        bids = orderbook.get("bids", [])[:10]
        asks = orderbook.get("asks", [])[:10]

        # Reverse asks for display
        asks = list(reversed(asks))

        # Add spread row
        if bids and asks:
            spread = orderbook.get("spread", 0)
            spread_pct = orderbook.get("spread_percentage", 0)
            table.add_row(
                "", "",
                f"Spread: {spread:.4f} ({spread_pct:.3f}%)",
                "", "",
                style="bold yellow"
            )

        # Add ask rows
        for ask in asks:
            price = ask.get("price", 0)
            volume = ask.get("volume", 0)
            table.add_row(
                "", "",
                f"{price:.2f}",
                f"{price:.2f}",
                f"{volume:.4f}"
            )

        # Add mid price
        if "best_bid" in orderbook and "best_ask" in orderbook:
            mid_price = (orderbook["best_bid"] + orderbook["best_ask"]) / 2
            table.add_row(
                "", "",
                f"━━ {mid_price:.2f} ━━",
                "", "",
                style="bold cyan"
            )

        # Add bid rows
        for bid in bids:
            price = bid.get("price", 0)
            volume = bid.get("volume", 0)
            table.add_row(
                f"{volume:.4f}",
                f"{price:.2f}",
                f"{price:.2f}",
                "", ""
            )

        return Panel(
            table,
            title=f"📈 Order Book - {self.current_symbol}",
            border_style="cyan"
        )

    def create_stats_panel(self) -> Panel:
        """Create market statistics panel"""
        stats = self.stats_data.get(self.current_symbol, {})

        if not stats:
            return Panel(
                Align.center(Text("No statistics available", style="dim")),
                title="📊 Market Stats",
                border_style="green"
            )

        # Format stats in columns
        col1 = Text()
        col1.append("Best Bid: ", style="bold")
        col1.append(f"${stats.get('best_bid', 0):,.2f}\n", style="green")
        col1.append("Bid Volume: ", style="bold")
        col1.append(f"{stats.get('bid_volume_total', 0):,.2f}\n", style="green")
        col1.append("Bid Value: ", style="bold")
        col1.append(f"${stats.get('bid_value_total', 0):,.0f}", style="green")

        col2 = Text()
        col2.append("Best Ask: ", style="bold")
        col2.append(f"${stats.get('best_ask', 0):,.2f}\n", style="red")
        col2.append("Ask Volume: ", style="bold")
        col2.append(f"{stats.get('ask_volume_total', 0):,.2f}\n", style="red")
        col2.append("Ask Value: ", style="bold")
        col2.append(f"${stats.get('ask_value_total', 0):,.0f}", style="red")

        col3 = Text()
        col3.append("Mid Price: ", style="bold")
        col3.append(f"${stats.get('mid_price', 0):,.2f}\n", style="yellow")
        col3.append("Spread: ", style="bold")
        col3.append(f"{stats.get('spread_percentage', 0):.3f}%\n", style="yellow")
        col3.append("Imbalance: ", style="bold")
        imbalance = stats.get('imbalance', 0)
        imb_color = "green" if imbalance > 0 else "red" if imbalance < 0 else "yellow"
        col3.append(f"{imbalance:.3f}", style=imb_color)

        columns = Columns([col1, col2, col3], padding=2, expand=True)

        return Panel(
            columns,
            title="📊 Market Statistics",
            border_style="green"
        )

    def create_whales_panel(self) -> Panel:
        """Create whale orders panel"""
        if not self.show_whales:
            return Panel(
                Align.center(Text("Whale alerts disabled", style="dim")),
                title="🐋 Whale Orders",
                border_style="yellow"
            )

        if not self.whale_data:
            return Panel(
                Align.center(Text("No whale orders detected", style="dim")),
                title="🐋 Whale Orders",
                border_style="yellow"
            )

        # Create whale table
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Time", width=8)
        table.add_column("Symbol", width=10)
        table.add_column("Side", width=6)
        table.add_column("Price", width=10)
        table.add_column("Value", width=12)
        table.add_column("Dist%", width=6)

        for whale in list(self.whale_data)[:10]:  # Show last 10
            timestamp = datetime.fromisoformat(whale.get('timestamp', '').replace('Z', '+00:00'))
            time_str = timestamp.strftime('%H:%M:%S')

            side = whale.get('side', '')
            side_color = "green" if side == "bid" else "red"

            value = whale.get('value_usdt', 0)

            table.add_row(
                time_str,
                whale.get('symbol', ''),
                side.upper(),
                f"${whale.get('price', 0):.2f}",
                f"${value:,.0f}",
                f"{whale.get('distance_from_mid', 0):.1f}%",
                style=side_color
            )

        return Panel(
            table,
            title=f"🐋 Recent Whale Orders ({len(self.whale_data)} total)",
            border_style="yellow"
        )

    def create_depth_panel(self) -> Panel:
        """Create market depth panel"""
        if not self.show_depth:
            return Panel(
                Align.center(Text("Depth view disabled", style="dim")),
                title="📏 Market Depth",
                border_style="magenta"
            )

        depth_data = self.depth_data.get(self.current_symbol, [])

        if not depth_data:
            return Panel(
                Align.center(Text("No depth data available", style="dim")),
                title="📏 Market Depth",
                border_style="magenta"
            )

        # Create depth table
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Depth", width=8)
        table.add_column("Bid Vol", width=12, style="green")
        table.add_column("Ask Vol", width=12, style="red")
        table.add_column("Ratio", width=10)

        for depth in depth_data:
            depth_pct = depth.get('depth_percentage', '0%')
            bid_vol = depth.get('bid_volume', 0)
            ask_vol = depth.get('ask_volume', 0)

            # Calculate ratio
            total = bid_vol + ask_vol
            ratio = (bid_vol / total * 100) if total > 0 else 50

            # Color based on ratio
            ratio_color = "green" if ratio > 60 else "red" if ratio < 40 else "yellow"

            table.add_row(
                str(depth_pct),
                f"{bid_vol:,.1f}",
                f"{ask_vol:,.1f}",
                f"{ratio:.1f}%",
                style=ratio_color if ratio != 50 else "dim"
            )

        return Panel(
            table,
            title="📏 Market Depth Analysis",
            border_style="magenta"
        )

    def create_footer(self) -> Panel:
        """Create footer panel with controls"""
        footer_text = Text()
        footer_text.append("[TAB]", style="bold cyan")
        footer_text.append(" Switch Symbol  ", style="dim")
        footer_text.append("[W]", style="bold cyan")
        footer_text.append(" Toggle Whales  ", style="dim")
        footer_text.append("[D]", style="bold cyan")
        footer_text.append(" Toggle Depth  ", style="dim")
        footer_text.append("[R]", style="bold cyan")
        footer_text.append(" Refresh  ", style="dim")
        footer_text.append("[Q]", style="bold cyan")
        footer_text.append(" Quit", style="dim")

        return Panel(
            Align.center(footer_text),
            style="dim white on black"
        )

    async def fetch_data(self):
        """Fetch all data from API"""
        symbol = self.current_symbol

        # Fetch data concurrently
        tasks = [
            self.api.get_orderbook(symbol),
            self.api.get_stats(symbol),
            self.api.get_recent_whales(symbol, limit=20),
            self.api.get_market_depth(symbol)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Update data
        if not isinstance(results[0], Exception):
            self.orderbook_data[symbol] = results[0]

        if not isinstance(results[1], Exception):
            self.stats_data[symbol] = results[1]

        if not isinstance(results[2], Exception) and results[2]:
            # Add new whale orders
            for whale in results[2]:
                if whale not in self.whale_data:
                    self.whale_data.append(whale)

        if not isinstance(results[3], Exception):
            self.depth_data[symbol] = results[3]

        self.last_update = datetime.now()

    def render(self) -> Layout:
        """Render the complete UI"""
        layout = self.create_layout()

        # Update panels
        layout["header"].update(self.create_header())
        layout["orderbook"].update(self.create_orderbook_panel())
        layout["stats"].update(self.create_stats_panel())
        layout["whales"].update(self.create_whales_panel())
        layout["depth"].update(self.create_depth_panel())
        layout["footer"].update(self.create_footer())

        return layout

    def check_keyboard_input(self):
        """Check for keyboard input without blocking"""
        try:
            import sys, select
            # Check if input is available
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                import termios, tty
                # Save terminal settings
                old_settings = termios.tcgetattr(sys.stdin)
                try:
                    # Set to raw mode temporarily
                    tty.setraw(sys.stdin.fileno())
                    key = sys.stdin.read(1).lower()

                    if key == 'q':
                        self.running = False
                        return True
                    elif key == '\t':  # Tab key
                        self.current_symbol_idx = (self.current_symbol_idx + 1) % len(self.symbols)
                    elif key == 'w':
                        self.show_whales = not self.show_whales
                    elif key == 'd':
                        self.show_depth = not self.show_depth
                    elif key == 'r':
                        asyncio.create_task(self.fetch_data())
                finally:
                    # Restore terminal settings
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        except:
            # On Windows or if termios not available, use simpler approach
            pass
        return False

    async def run(self):
        """Main UI loop"""
        # Initial data fetch
        await self.fetch_data()

        try:
            with Live(
                self.render(),
                console=self.console,
                refresh_per_second=2,
                screen=True
            ) as live:
                while self.running:
                    # Check for keyboard input
                    if self.check_keyboard_input():
                        break

                    # Update data
                    await self.fetch_data()
                    live.update(self.render())

                    # Small sleep to prevent CPU spinning
                    await asyncio.sleep(self.refresh_rate)

        finally:
            await self.api.close()
            self.console.clear()
            self.console.print("[bold green]Goodbye![/bold green]")


@click.command()
@click.option(
    '--api-url',
    default='http://localhost:8000',
    help='API base URL'
)
@click.option(
    '--symbols',
    default='BTC_USDT,ETH_USDT',
    help='Comma-separated list of symbols to monitor'
)
@click.option(
    '--refresh-rate',
    default=1.0,
    type=float,
    help='Refresh rate in seconds'
)
def main(api_url: str, symbols: str, refresh_rate: float):
    """Real-time Order Book Terminal UI"""

    # Parse symbols
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]

    if not symbol_list:
        click.echo("Error: No valid symbols provided", err=True)
        sys.exit(1)

    # Create and run UI
    ui = OrderBookUI(api_url, symbol_list, refresh_rate)

    try:
        asyncio.run(ui.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()