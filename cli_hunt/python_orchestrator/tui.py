import logging
import threading
from collections import OrderedDict
from datetime import datetime

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Footer, Header, Log, Static

# --- Custom Messages for thread-safe UI updates ---


class LogMessage(Message):
    """Message to add a line to the TUI log viewer."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__()


class ChallengeUpdate(Message):
    """Message to update the status of a single challenge in the TUI table."""

    def __init__(self, address: str, challenge_id: str, status: str) -> None:
        self.address = address
        self.challenge_id = challenge_id
        self.status = status
        super().__init__()


class RefreshTable(Message):
    """Message to signal a full refresh of the TUI table."""

    pass


class UpdateSummary(Message):
    """Message to signal a summary update without full table refresh."""

    pass


# --- The Main TUI Application ---


class OrchestratorTUI(App):
    """A Textual TUI for the Midnight Scavenger Hunt orchestrator."""

    TITLE = "Midnight Scavenger Hunt Orchestrator"
    
    CSS = """
    #summary {
        background: $boost;
        color: $text;
        height: auto;
        padding: 1;
        text-align: center;
        text-style: bold;
    }
    """

    def __init__(
        self, db_manager, worker_functions: dict, worker_args: dict, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.db_manager = db_manager
        self.worker_functions = worker_functions
        self.worker_args = worker_args
        self.stop_event = threading.Event()

        # Internal state for the table
        self._addresses = []
        self._challenge_ids = OrderedDict()  # challenge_id -> short_id

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Static(id="summary", expand=False)
        with VerticalScroll():
            yield DataTable(id="challenges_table", cursor_type="row")
        yield Log(id="logs", auto_scroll=True, max_lines=1000)
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.log_widget = self.query_one(Log)
        self.table = self.query_one(DataTable)
        self.summary_widget = self.query_one("#summary", Static)

        self.log_widget.write_line("TUI mounted. Initializing table...")
        self.update_summary()
        self.refresh_table_structure()

        self.log_widget.write_line("Starting background worker threads...")
        self.run_fetcher_worker()
        self.run_solver_worker()
        self.run_saver_worker()

    def _get_status_display(self, status: str) -> str:
        """Return a user-friendly (emoji) string for a status."""
        status_map = {
            "available": "⏳ Avail",
            "solving": "⚙️ Solving",
            "solved": "✅ Solved",
            "validated": "🏆 Validated",
            "expired": "❌ Expired",
            "submission_error": "❗️ Error",
            "unsubmitted": "⚠️ Unsub",
        }
        return status_map.get(status, status)

    def refresh_table_structure(self) -> None:
        """
        Initializes or rebuilds the entire table structure (columns and rows).
        It will always display the latest 15 challenges across all addresses.
        """
        self.table.clear(columns=True)

        # --- Get current data from DB ---
        self._addresses = self.db_manager.get_addresses()
        if not self._addresses:
            self.log_widget.write_line("No addresses found. Table is empty.")
            return

        all_challenge_ids = set()
        for addr in self._addresses:
            for c in self.db_manager.get_challenge_queue(addr):
                all_challenge_ids.add(c["challengeId"])

        # Sort challenges and keep only the most recent 15
        sorted_challenges = sorted(list(all_challenge_ids))
        if len(sorted_challenges) > 15:
            sorted_challenges = sorted_challenges[-15:]

        self._challenge_ids = OrderedDict((cid, cid[3:]) for cid in sorted_challenges)

        # --- Add Columns ---
        self.table.add_column("Address", key="address")
        for cid, short_cid in self._challenge_ids.items():
            self.table.add_column(short_cid, key=cid)

        # --- Add Rows ---
        for addr in self._addresses:
            short_addr = f"{addr[:6]}...{addr[-4:]}"
            # Create a row with placeholders. We'll populate it next.
            row_data = [short_addr] + ["-"] * len(self._challenge_ids)
            self.table.add_row(*row_data, key=addr)

        # --- Populate all cells with current status for displayed challenges ---
        for addr in self._addresses:
            # Only consider challenges that are actually displayed in the table
            displayed_challenges = [
                c
                for c in self.db_manager.get_challenge_queue(addr)
                if c["challengeId"] in self._challenge_ids
            ]
            for c in displayed_challenges:
                self.post_message(ChallengeUpdate(addr, c["challengeId"], c["status"]))

    # --- Message Handlers ---

    def on_log_message(self, message: LogMessage) -> None:
        """Display a log message from a worker."""
        now = datetime.now().strftime("%H:%M:%S")
        self.log_widget.write_line(f"[{now}] {message.message}")
        logging.info(message.message)  # Also write to the actual log file

    def on_challenge_update(self, message: ChallengeUpdate) -> None:
        """Update a single cell in the DataTable, if the challenge is currently displayed."""
        if message.challenge_id in self._challenge_ids:
            try:
                display_status = self._get_status_display(message.status)
                self.table.update_cell(
                    message.address, message.challenge_id, display_status
                )
            except KeyError:
                # This should ideally not happen if _challenge_ids is consistent with table columns
                self.log_widget.write_line(
                    f"[Warning] Could not update cell (KeyError) for displayed challenge: "
                    f"{message.address[:6]}/{message.challenge_id}. This indicates a potential sync issue."
                )
        # If the challenge ID is not in _challenge_ids, we simply ignore the update
        # as it's not a challenge we're currently displaying.

    def on_refresh_table(self, message: RefreshTable) -> None:
        """Handle request to perform a full table refresh."""
        self.log_widget.write_line("Refreshing table data...")
        self.update_summary()
        self.refresh_table_structure()

    def on_update_summary(self, message: UpdateSummary) -> None:
        """Handle request to update just the summary."""
        self.update_summary()

    def update_summary(self) -> None:
        """Update the summary widget with mining statistics."""
        import requests
        
        # Fetch work_to_star_rate from API
        work_to_star_rates = [3724076, 2133655, 2396362, 3521664, 2233377]  # Fallback values
        try:
            response = requests.get("https://scavenger.prod.gd.midnighttge.io/work_to_star_rate", timeout=5)
            response.raise_for_status()
            api_rates = response.json()
            if isinstance(api_rates, list) and len(api_rates) > 0:
                work_to_star_rates = api_rates
        except Exception:
            pass  # Silently use fallback
        
        addresses = self.db_manager.get_addresses()
        if not addresses:
            self.summary_widget.update("No addresses found.")
            return
        
        # Calculate average rate for current day estimation (exclude first day)
        avg_rate = sum(work_to_star_rates[1:]) / len(work_to_star_rates[1:]) if len(work_to_star_rates) > 1 else work_to_star_rates[0]
        current_day = len(work_to_star_rates) + 1  # Next day after known rates
        
        grand_total_star = 0
        current_day_star = 0
        total_validated = 0
        current_day_validated = 0
        
        for address in addresses:
            challenges = self.db_manager.get_challenge_queue(address)
            
            for c in challenges:
                if c.get("status") == "validated":
                    campaign_day = c.get("campaignDay")
                    if campaign_day is not None:
                        total_validated += 1
                        # Day is 1-indexed, list is 0-indexed
                        if campaign_day - 1 < len(work_to_star_rates):
                            star_per_solution = work_to_star_rates[campaign_day - 1]
                            grand_total_star += star_per_solution
                        # Current day estimation
                        if campaign_day == current_day:
                            current_day_validated += 1
                            current_day_star += avg_rate
        
        grand_total_night = grand_total_star / 1_000_000
        current_day_night = current_day_star / 1_000_000
        estimated_total_night = grand_total_night + current_day_night
        
        summary_text = (
            f"Mining Summary: {len(addresses)} address(es) | "
            f"{total_validated} solutions | "
            f"Earned: {grand_total_night:.3f} $NIGHT"
        )
        
        if current_day_validated > 0:
            summary_text += f" | Day {current_day} Est: ~{current_day_night:.3f} $NIGHT ({current_day_validated} sol) | Total Est: {estimated_total_night:.3f} $NIGHT"
        
        self.summary_widget.update(summary_text)

    # --- Actions ---

    def action_quit(self) -> None:
        """Action to quit the application, triggered by Ctrl+C."""
        self.log_widget.write_line("Shutdown signal received. Stopping threads...")
        self.stop_event.set()
        # Give workers a moment to notice the event. A proper implementation would join them.
        self.log_widget.write_line("Performing final save...")
        self.db_manager.save_to_disk()
        self.log_widget.write_line("Exiting.")
        self.exit()

    # --- Worker Definitions ---

    @work(name="fetcher", group="workers", thread=True)
    def run_fetcher_worker(self) -> None:
        """Runs the fetcher logic in a background thread."""
        fetcher_func = self.worker_functions["fetcher"]
        fetch_interval_minutes = self.worker_args.get("fetch_interval_minutes")
        fetcher_func(self.db_manager, self.stop_event, self, fetch_interval_minutes)

    @work(name="solver", group="workers", thread=True)
    def run_solver_worker(self) -> None:
        """Runs the solver logic in a background thread."""
        solver_func = self.worker_functions["solver"]
        solve_interval = self.worker_args["solve_interval"]
        max_solvers = self.worker_args["max_solvers"]
        solver_func(
            self.db_manager,
            self.stop_event,
            solve_interval,
            self,
            max_solvers,
        )

    @work(name="saver", group="workers", thread=True)
    def run_saver_worker(self) -> None:
        """Runs the database saver logic in a background thread."""
        saver_func = self.worker_functions["saver"]
        interval = self.worker_args["save_interval"]
        saver_func(self.db_manager, self.stop_event, interval, self)
