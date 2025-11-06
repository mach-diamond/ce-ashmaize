import argparse
import json
import logging
import os
import concurrent.futures
import subprocess
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import requests
from tui import ChallengeUpdate, LogMessage, OrchestratorTUI, RefreshTable

# --- Constants ---
DB_FILE = "challenges.json"
JOURNAL_FILE = "challenges.json.journal"
LOG_FILE = "orchestrator.log"
MANUAL_CHALLENGES_DIR = "manual-challenges"
SOLUTIONS_DIR = "solutions"
RUST_SOLVER_PATH = (
    "../rust_solver/target/release/ashmaize-solver"  # Assuming it's built
)
FETCH_INTERVAL = 5 * 60  # 5 minutes between checks
USER_AGENT = "ce-ashmaize-miner/1.0"  # User-Agent header
DEFAULT_SOLVE_INTERVAL = 1 * 60  # 30 minutes
DEFAULT_SAVE_INTERVAL = 2 * 60  # 2 minutes


# --- Logging Setup ---
def setup_logging():
    """Sets up logging to a file."""
    # Configure logging to write to a file, overwriting it each time
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename=LOG_FILE,
        filemode="w",  # 'w' to overwrite the log on each run
    )
    # Silence noisy libraries
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def ensure_directories():
    """Creates necessary directories if they don't exist."""
    os.makedirs(MANUAL_CHALLENGES_DIR, exist_ok=True)
    os.makedirs(SOLUTIONS_DIR, exist_ok=True)
    logging.info(f"Ensured directories exist: {MANUAL_CHALLENGES_DIR}, {SOLUTIONS_DIR}")


# --- DatabaseManager for Thread-Safe Operations ---
class DatabaseManager:
    """Manages the in-memory database with thread-safe operations and journaling."""

    def __init__(self):
        self._db = {}
        # A lock is still good practice for data consistency between background workers.
        self._lock = threading.Lock()
        self._load_from_disk()
        self._replay_journal()
        self._reset_solving_challenges_on_startup()

    def _load_from_disk(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r") as f:
                    self._db = json.load(f)
                logging.info("Loaded main database from challenges.json.")
            except json.JSONDecodeError:
                logging.error(
                    f"Error reading {DB_FILE}, starting with an empty database."
                )
                self._db = {}

    def _apply_add_challenge(self, address, challenge):
        if address in self._db:
            queue = self._db[address].get("challenge_queue", [])
            if not any(c["challengeId"] == challenge["challengeId"] for c in queue):
                queue.append(challenge)
                queue.sort(key=lambda c: c["challengeId"])

    def _apply_update_challenge(self, address, challenge_id, update):
        if address in self._db:
            queue = self._db[address].get("challenge_queue", [])
            for c in queue:
                if c["challengeId"] == challenge_id:
                    c.update(update)
                    break

    def _replay_journal(self):
        if not os.path.exists(JOURNAL_FILE):
            return

        logging.info("Replaying journal...")
        replayed_count = 0
        with open(JOURNAL_FILE, "r") as f:
            for line in f:
                try:
                    log_entry = json.loads(line)
                    action = log_entry.get("action")
                    payload = log_entry.get("payload")
                    address = payload.get("address")

                    if action == "add_challenge":
                        self._apply_add_challenge(address, payload["challenge"])
                    elif action == "update_challenge":
                        self._apply_update_challenge(
                            address, payload["challengeId"], payload["update"]
                        )
                    replayed_count += 1
                except (json.JSONDecodeError, KeyError):
                    logging.warning(f"Skipping malformed journal entry: {line.strip()}")
        if replayed_count > 0:
            logging.info(f"Replayed {replayed_count} journal entries.")

    def _reset_solving_challenges_on_startup(self):
        """Resets any 'solving' challenges to 'available' at startup."""
        reset_count = 0
        for address, data in self._db.items():
            queue = data.get("challenge_queue", [])
            for c in queue:
                if c.get("status") == "solving":
                    c["status"] = "available"
                    reset_count += 1
        if reset_count > 0:
            logging.warning(
                f"Reset {reset_count} challenges from 'solving' to 'available' status on startup."
            )

    def _log_to_journal(self, action, payload):
        try:
            with open(JOURNAL_FILE, "a") as f:
                log_entry = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "action": action,
                    "payload": payload,
                }
                f.write(json.dumps(log_entry) + "\n")
        except IOError as e:
            logging.critical(f"CRITICAL: Could not write to journal file: {e}")

    def add_challenge(self, address, challenge):
        with self._lock:
            queue = self._db.get(address, {}).get("challenge_queue", [])
            if any(c["challengeId"] == challenge["challengeId"] for c in queue):
                return False

            self._log_to_journal(
                "add_challenge", {"address": address, "challenge": challenge}
            )
            self._apply_add_challenge(address, challenge)
            return True

    def update_challenge(self, address, challenge_id, update):
        with self._lock:
            self._log_to_journal(
                "update_challenge",
                {"address": address, "challengeId": challenge_id, "update": update},
            )
            self._apply_update_challenge(address, challenge_id, update)
            # Return the updated status if it exists
            return update.get("status")

    def get_addresses(self):
        with self._lock:
            return list(self._db.keys())

    def get_challenge_queue(self, address):
        with self._lock:
            return deepcopy(self._db.get(address, {}).get("challenge_queue", []))

    def save_to_disk(self):
        logging.info("Saving database to disk...")
        with self._lock:
            try:
                with open(DB_FILE, "w") as f:
                    json.dump(self._db, f, indent=4)
                if os.path.exists(JOURNAL_FILE):
                    open(JOURNAL_FILE, "w").close()
                logging.info("Database saved successfully.")
            except IOError as e:
                logging.error(f"Error saving database: {e}")


# --- Worker Functions ---
# Note: These are now designed to be run by a Textual @work decorator.
# They accept a `tui_app` object to post messages back to the UI thread.


def fetcher_worker(db_manager, stop_event, tui_app, fetch_interval_minutes=None):
    tui_app.post_message(LogMessage("Fetcher thread started."))
    
    # Determine fetch mode
    use_smart_timing = fetch_interval_minutes is None
    
    if use_smart_timing:
        tui_app.post_message(LogMessage("Using smart timing: fetching 5 minutes after each hour"))
    else:
        tui_app.post_message(LogMessage(f"Using manual interval: fetching every {fetch_interval_minutes} minutes"))
    
    # Calculate the next fetch time: 5 minutes after the next hour
    def get_next_fetch_time():
        now = datetime.now(timezone.utc)
        if use_smart_timing:
            # Get the start of the next hour
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            # Add 5 minutes
            return next_hour + timedelta(minutes=5)
        else:
            # Just add the interval from now
            return now + timedelta(minutes=fetch_interval_minutes)
    
    def load_manual_challenges():
        """Loads challenges from manual-challenges folder."""
        if not os.path.exists(MANUAL_CHALLENGES_DIR):
            return
        
        manual_files = [f for f in os.listdir(MANUAL_CHALLENGES_DIR) if f.endswith('.json')]
        if not manual_files:
            return
        
        tui_app.post_message(LogMessage(f"Found {len(manual_files)} manual challenge file(s)..."))
        
        for filename in manual_files:
            filepath = os.path.join(MANUAL_CHALLENGES_DIR, filename)
            try:
                with open(filepath, 'r') as f:
                    challenge_data = json.load(f)
                
                # Support both raw API response and just the challenge object
                if "challenge" in challenge_data:
                    challenge_data = challenge_data["challenge"]
                
                new_challenge = {
                    "challengeId": challenge_data["challenge_id"],
                    "challengeNumber": challenge_data["challenge_number"],
                    "campaignDay": challenge_data["day"],
                    "difficulty": challenge_data["difficulty"],
                    "status": "available",
                    "noPreMine": challenge_data["no_pre_mine"],
                    "noPreMineHour": challenge_data["no_pre_mine_hour"],
                    "latestSubmission": challenge_data["latest_submission"],
                    "availableAt": challenge_data["issued_at"],
                }
                
                addresses = db_manager.get_addresses()
                added = False
                for address in addresses:
                    if db_manager.add_challenge(address, deepcopy(new_challenge)):
                        tui_app.post_message(
                            LogMessage(
                                f"Manual challenge {new_challenge['challengeId']} added for {address[:10]}..."
                            )
                        )
                        added = True
                
                if added:
                    # Move processed file to avoid re-importing
                    processed_path = filepath + ".processed"
                    os.rename(filepath, processed_path)
                    tui_app.post_message(LogMessage(f"Processed {filename}"))
                    tui_app.post_message(RefreshTable())
                    
            except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
                tui_app.post_message(LogMessage(f"Error loading manual challenge {filename}: {e}"))
    
    def fetch_challenges():
        """Performs the actual challenge fetch. Returns True if successful."""
        tui_app.post_message(LogMessage("Fetching new challenges..."))
        addresses = db_manager.get_addresses()
        if not addresses:
            tui_app.post_message(
                LogMessage("No addresses in database, fetcher is idle.")
            )
            return True  # Not really an error
        
        try:
            headers = {
                "User-Agent": "Go-http-client/1.1",
                "Accept": "application/json"
            }
            response = requests.get("https://scavenger.prod.gd.midnighttge.io/challenge", headers=headers)
            response.raise_for_status()
            challenge_data = response.json()["challenge"]

            new_challenge = {
                "challengeId": challenge_data["challenge_id"],
                "challengeNumber": challenge_data["challenge_number"],
                "campaignDay": challenge_data["day"],
                "difficulty": challenge_data["difficulty"],
                "status": "available",
                "noPreMine": challenge_data["no_pre_mine"],
                "noPreMineHour": challenge_data["no_pre_mine_hour"],
                "latestSubmission": challenge_data["latest_submission"],
                "availableAt": challenge_data["issued_at"],
            }

            added = False
            for address in addresses:
                if db_manager.add_challenge(address, deepcopy(new_challenge)):
                    tui_app.post_message(
                        LogMessage(
                            f"New challenge {new_challenge['challengeId']} added for {address[:10]}..."
                        )
                    )
                    added = True

            if added:
                # Signal to the UI that a full refresh is needed to show the new column
                tui_app.post_message(RefreshTable())
            return True

        except requests.exceptions.RequestException as e:
            tui_app.post_message(LogMessage(f"Error fetching challenge: {e}"))
            # On rate limit or error, check for Retry-After header
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                retry_after = e.response.headers.get('Retry-After')
                if retry_after:
                    wait_time = int(retry_after)
                    tui_app.post_message(LogMessage(f"Rate limited. Waiting {wait_time} seconds..."))
                    stop_event.wait(wait_time)
            return False
        except json.JSONDecodeError:
            tui_app.post_message(
                LogMessage("Error decoding challenge API response.")
            )
            return False
    
    # Load manual challenges on startup
    tui_app.post_message(LogMessage("Checking for manual challenges..."))
    load_manual_challenges()
    
    # Fetch immediately on startup
    tui_app.post_message(LogMessage("Performing initial challenge fetch..."))
    fetch_challenges()
    
    # Schedule next fetch
    next_fetch_time = get_next_fetch_time()
    tui_app.post_message(LogMessage(f"Next fetch scheduled at: {next_fetch_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"))
    
    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        
        # Wait until it's time to fetch
        if now < next_fetch_time:
            wait_seconds = (next_fetch_time - now).total_seconds()
            if wait_seconds > 60:  # Only log if more than a minute away
                minutes_left = int(wait_seconds / 60)
                tui_app.post_message(LogMessage(f"Waiting {minutes_left} minutes until next fetch..."))
            stop_event.wait(min(60, wait_seconds))  # Check every minute or less
            continue
        
        # Time to fetch!
        load_manual_challenges()  # Check for manual challenges each cycle
        fetch_challenges()
        
        # Calculate next fetch time (5 minutes after next hour)
        next_fetch_time = get_next_fetch_time()
        tui_app.post_message(LogMessage(f"Next fetch scheduled at: {next_fetch_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"))
    
    logging.info("Fetcher thread stopped.")


def _solve_one_challenge(db_manager, tui_app, stop_event, address, challenge):
    """Solves a single challenge."""
    c = challenge  # for brevity
    msg = f"Attempting to solve challenge {c['challengeId']} for {address[:10]}..."
    tui_app.post_message(LogMessage(msg))
    
    # Check if we have a cached solution
    solution_filename = f"{address}_{c['challengeId']}.json"
    solution_path = os.path.join(SOLUTIONS_DIR, solution_filename)
    
    nonce = None
    if os.path.exists(solution_path):
        try:
            with open(solution_path, 'r') as f:
                solution_data = json.load(f)
                nonce = solution_data.get('nonce')
                if nonce:
                    tui_app.post_message(LogMessage(f"Found cached solution for {c['challengeId']}: {nonce}"))
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            tui_app.post_message(LogMessage(f"Error reading cached solution: {e}"))
            nonce = None
    
    # If no cached solution, solve it
    if not nonce:
        try:
            command = [
                RUST_SOLVER_PATH,
                "--address",
                address,
                "--challenge-id",
                c["challengeId"],
                "--difficulty",
                c["difficulty"],
                "--no-pre-mine",
                str(c["noPreMine"]),  # Convert boolean to string for subprocess
                "--latest-submission",
                c["latestSubmission"],
                "--no-pre-mine-hour",
                str(c["noPreMineHour"]),  # Convert to string for subprocess
            ]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            while process.poll() is None:
                if stop_event.is_set():
                    process.terminate()
                    tui_app.post_message(
                        LogMessage(f"Solver for {c['challengeId']} terminated by shutdown.")
                    )
                    # Revert status so it can be picked up again on restart
                    db_manager.update_challenge(
                        address, c["challengeId"], {"status": "available"}
                    )
                    return
                stop_event.wait(0.2)

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode,
                    command,
                    output=stdout,
                    stderr=stderr,
                )

            nonce = stdout.strip()
            tui_app.post_message(LogMessage(f"Found nonce: {nonce} for {c['challengeId']}"))
            
            # Save the solution immediately and mark as unsubmitted
            try:
                solution_data = {
                    "address": address,
                    "challengeId": c["challengeId"],
                    "nonce": nonce,
                    "solvedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                }
                with open(solution_path, 'w') as f:
                    json.dump(solution_data, f, indent=2)
                tui_app.post_message(LogMessage(f"Cached solution to {solution_filename}"))
                
                # Mark as unsubmitted
                db_manager.update_challenge(address, c["challengeId"], {"status": "unsubmitted", "salt": nonce})
                tui_app.post_message(ChallengeUpdate(address, c["challengeId"], "unsubmitted"))
            except IOError as e:
                tui_app.post_message(LogMessage(f"Warning: Could not cache solution: {e}"))

        except subprocess.CalledProcessError as e:
            msg = f"Rust solver error for {c['challengeId']}: {e.stderr.strip()}"
            tui_app.post_message(LogMessage(msg))
            db_manager.update_challenge(address, c["challengeId"], {"status": "available"})
            tui_app.post_message(ChallengeUpdate(address, c["challengeId"], "available"))
            return
        except Exception as e:
            msg = f"An unexpected error occurred during solving: {e}"
            tui_app.post_message(LogMessage(msg))
            db_manager.update_challenge(address, c["challengeId"], {"status": "available"})
            tui_app.post_message(ChallengeUpdate(address, c["challengeId"], "available"))
            return
    
    # Now try to submit (whether from cache or freshly solved)
    # Only attempt submission if we have a nonce
    if nonce:
        solved_time = datetime.now(timezone.utc)
        try:
            submit_url = (
                f"https://scavenger.prod.gd.midnighttge.io/solution/{address}/{c['challengeId']}/{nonce}"
            )
            headers = {
                "User-Agent": "Go-http-client/1.1",
                "Accept": "application/json"
            }
            submit_response = requests.post(submit_url, headers=headers)
            submit_response.raise_for_status()
            validated_time = datetime.now(timezone.utc)
            tui_app.post_message(
                LogMessage(f"Solution submitted successfully for {c['challengeId']}")
            )

            try:
                submission_data = submit_response.json()
                crypto_receipt = submission_data.get("crypto_receipt")

                update = {}
                if crypto_receipt:
                    update = {
                        "status": "validated",
                        "solvedAt": solved_time.isoformat(timespec="milliseconds").replace(
                            "+00:00", "Z"
                        ),
                        "submittedAt": solved_time.isoformat(
                            timespec="milliseconds"
                        ).replace("+00:00", "Z"),
                        "validatedAt": validated_time.isoformat(
                            timespec="milliseconds"
                        ).replace("+00:00", "Z"),
                        "salt": nonce,
                        "cryptoReceipt": crypto_receipt,
                    }
                    tui_app.post_message(
                        LogMessage(f"Successfully validated challenge {c['challengeId']}")
                    )
                    # Rename cached solution on successful validation
                    if os.path.exists(solution_path):
                        validated_path = solution_path.replace('.json', '.validated')
                        os.rename(solution_path, validated_path)
                        tui_app.post_message(LogMessage(f"Archived solution as validated"))
                else:
                    update = {
                        "status": "solved",  # Submitted but not validated with receipt
                        "solvedAt": solved_time.isoformat(timespec="milliseconds").replace(
                            "+00:00", "Z"
                        ),
                        "salt": nonce,
                    }
                    tui_app.post_message(
                        LogMessage(
                            f"Submission for {c['challengeId']} OK but no crypto_receipt."
                        )
                    )

                updated_status = db_manager.update_challenge(
                    address, c["challengeId"], update
                )
                if updated_status:
                    tui_app.post_message(
                        ChallengeUpdate(address, c["challengeId"], updated_status)
                    )

            except json.JSONDecodeError:
                msg = f"Failed to decode submission response for {c['challengeId']}."
                tui_app.post_message(LogMessage(msg))
                update = {"status": "submission_error", "salt": nonce}
                updated_status = db_manager.update_challenge(
                    address, c["challengeId"], update
                )
                if updated_status:
                    tui_app.post_message(
                        ChallengeUpdate(address, c["challengeId"], updated_status)
                    )

        except requests.exceptions.RequestException as e:  # ty: ignore
            msg = f"Error submitting solution for {c['challengeId']}: {e}"
            tui_app.post_message(LogMessage(msg))
            # Keep solution cached as .json and mark as unsubmitted
            tui_app.post_message(LogMessage(f"Solution cached. Will retry submission later."))
            db_manager.update_challenge(address, c["challengeId"], {"status": "unsubmitted", "salt": nonce})
            tui_app.post_message(ChallengeUpdate(address, c["challengeId"], "unsubmitted"))
        except Exception as e:
            msg = f"An unexpected error occurred during submission: {e}"
            tui_app.post_message(LogMessage(msg))
            # Keep solution cached and mark as unsubmitted
            db_manager.update_challenge(address, c["challengeId"], {"status": "unsubmitted", "salt": nonce})
            tui_app.post_message(ChallengeUpdate(address, c["challengeId"], "unsubmitted"))


def solver_worker(db_manager, stop_event, solve_interval, tui_app, max_solvers):
    tui_app.post_message(
        LogMessage(
            f"Solver thread started with {max_solvers} workers. Polling every {solve_interval / 60:.1f} minutes."
        )
    )

    # The executor should live for the duration of the worker
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_solvers) as executor:
        # Store futures for active tasks
        active_futures = set()
        last_logged_check_time = datetime.min.replace(
            tzinfo=timezone.utc
        )  # Initialize with timezone-aware datetime

        while not stop_event.is_set():
            now = datetime.now(timezone.utc)
            if (now - last_logged_check_time) >= timedelta(seconds=solve_interval):
                tui_app.post_message(LogMessage("Checking for challenges to solve..."))
                last_logged_check_time = now

            # Clean up completed futures
            done_futures = {f for f in active_futures if f.done()}
            for f in done_futures:
                active_futures.remove(f)

            available_slots = max_solvers - len(active_futures)
            if available_slots <= 0:
                if last_logged_check_time == now:
                    tui_app.post_message(
                        LogMessage(
                            f"Solver pool full ({len(active_futures)}/{max_solvers}). Waiting for slots."
                        )
                    )

            challenges_dispatched_this_round = 0
            if available_slots > 0:
                addresses = db_manager.get_addresses()
                now = datetime.now(timezone.utc)
                should_break_outer_loop = False

                for address in addresses:
                    challenges = db_manager.get_challenge_queue(address)
                    for c in challenges:
                        # Only process available challenges (not unsubmitted)
                        if c["status"] == "available":
                            latest_submission = datetime.fromisoformat(
                                c["latestSubmission"].replace("Z", "+00:00")
                            )
                            if now > latest_submission:
                                # Expire challenge
                                updated_status = db_manager.update_challenge(
                                    address, c["challengeId"], {"status": "expired"}
                                )
                                if updated_status:
                                    msg = f"Challenge {c['challengeId']} for {address[:10]}... has expired."
                                    tui_app.post_message(LogMessage(msg))
                                    tui_app.post_message(
                                        ChallengeUpdate(
                                            address, c["challengeId"], updated_status
                                        )
                                    )
                            else:
                                if available_slots > 0:
                                    # Claim the challenge by updating its status
                                    # This update is protected by DatabaseManager's lock
                                    updated_status = db_manager.update_challenge(
                                        address, c["challengeId"], {"status": "solving"}
                                    )
                                    if updated_status:
                                        tui_app.post_message(
                                            ChallengeUpdate(
                                                address,
                                                c["challengeId"],
                                                updated_status,
                                            )
                                        )
                                        # Submit claimed challenge to the thread pool
                                        future = executor.submit(
                                            _solve_one_challenge,
                                            db_manager,
                                            tui_app,
                                            stop_event,
                                            address,
                                            deepcopy(c),  # Pass a deepcopy
                                        )
                                        active_futures.add(future)
                                        challenges_dispatched_this_round += 1
                                        available_slots -= 1
                                else:
                                    # No more slots available in the current pass
                                    should_break_outer_loop = True
                                    break  # Exit inner challenge loop
                    if should_break_outer_loop:
                        break  # Exit outer address loop

                if challenges_dispatched_this_round > 0:
                    tui_app.post_message(
                        LogMessage(
                            f"Dispatched {challenges_dispatched_this_round} new challenges. "
                            f"{len(active_futures)} active solvers."
                        )
                    )
                elif len(active_futures) == 0 and challenges_dispatched_this_round == 0:
                    tui_app.post_message(LogMessage("No available challenges found."))

            # If all slots are full, wait for one future to complete, or a short timeout
            if len(active_futures) >= max_solvers and active_futures:
                # Wait for at least one task to complete or a short period if none are done quickly
                concurrent.futures.wait(
                    active_futures,
                    timeout=1,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
            else:
                # If there are available slots (or no active tasks),
                # wait the full solve_interval before checking for *new* challenges again.
                stop_event.wait(solve_interval)

    logging.info("Solver thread stopped.")


def saver_worker(db_manager, stop_event, interval, tui_app):
    tui_app.post_message(
        LogMessage(
            f"Saver thread started. Saving to disk every {interval / 60:.1f} minutes."
        )
    )
    while not stop_event.is_set():
        stop_event.wait(interval)
        if stop_event.is_set():
            break
        tui_app.post_message(LogMessage("Performing periodic save..."))
        db_manager.save_to_disk()
    logging.info("Saver thread stopped.")


# --- Main Application Logic ---
def init_db(json_files):
    """Initializes or updates the main database file from JSON inputs."""
    logging.info("Initializing or updating database file...")
    db = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                db = json.load(f)
        except json.JSONDecodeError:
            logging.warning(f"Could not read existing {DB_FILE}, starting fresh.")

    for file_path in json_files:
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                address = data.get("registration_receipt", {}).get("walletAddress")
                if not address:
                    logging.warning(f"Could not find address in {file_path}, skipping.")
                    continue

                if address not in db:
                    challenge_queue = data.get("challenge_queue", [])
                    challenge_queue.sort(key=lambda c: c["challengeId"])
                    db[address] = {
                        "registration_receipt": data.get("registration_receipt"),
                        "challenge_queue": challenge_queue,
                    }
                    logging.info(f"Initialized new address: {address}")
                else:
                    logging.info(f"Updating existing address: {address}")
                    existing_ids = {
                        c["challengeId"] for c in db[address].get("challenge_queue", [])
                    }
                    new_challenges = [
                        c
                        for c in data.get("challenge_queue", [])
                        if c["challengeId"] not in existing_ids
                    ]
                    if new_challenges:
                        db[address]["challenge_queue"].extend(new_challenges)
                        db[address]["challenge_queue"].sort(
                            key=lambda c: c["challengeId"]
                        )
                        logging.info(f"  Added {len(new_challenges)} new challenges.")
        except FileNotFoundError:
            logging.error(f"File not found: {file_path}")
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {file_path}")

    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

    if os.path.exists(JOURNAL_FILE):
        os.remove(JOURNAL_FILE)
        logging.info("Cleared existing journal file.")
    logging.info("Database file initialization complete.")


def retry_submissions(db_manager, max_workers=4):
    """Retry submitting all unsubmitted solutions without running the full miner."""
    print("Starting submission retry process...")
    ensure_directories()
    
    addresses = db_manager.get_addresses()
    if not addresses:
        print("No addresses found in database.")
        return
    
    # Collect all unsubmitted challenges
    unsubmitted_tasks = []
    for address in addresses:
        challenges = db_manager.get_challenge_queue(address)
        for c in challenges:
            if c["status"] == "unsubmitted":
                # Check if we have a cached solution
                solution_filename = f"{address}_{c['challengeId']}.json"
                solution_path = os.path.join(SOLUTIONS_DIR, solution_filename)
                if os.path.exists(solution_path):
                    unsubmitted_tasks.append((address, c, solution_path))
    
    if not unsubmitted_tasks:
        print("No unsubmitted solutions found.")
        return
    
    print(f"Found {len(unsubmitted_tasks)} unsubmitted solution(s) to retry.")
    
    def submit_one(address, challenge, solution_path):
        """Submit a single cached solution."""
        try:
            with open(solution_path, 'r') as f:
                solution_data = json.load(f)
                nonce = solution_data.get('nonce')
            
            if not nonce:
                print(f"  ✗ {challenge['challengeId'][:10]}... - No nonce in cached solution")
                return False
            
            print(f"  ↻ {challenge['challengeId'][:10]}... - Submitting...")
            submit_url = f"https://scavenger.prod.gd.midnighttge.io/solution/{address}/{challenge['challengeId']}/{nonce}"
            headers = {
                "User-Agent": "Go-http-client/1.1",
                "Accept": "application/json"
            }
            response = requests.post(submit_url, headers=headers)
            response.raise_for_status()
            
            submission_data = response.json()
            crypto_receipt = submission_data.get("crypto_receipt")
            
            if crypto_receipt:
                # Success! Update status and rename solution
                solved_time = datetime.now(timezone.utc)
                validated_time = datetime.now(timezone.utc)
                update = {
                    "status": "validated",
                    "solvedAt": solved_time.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "submittedAt": solved_time.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "validatedAt": validated_time.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "salt": nonce,
                    "cryptoReceipt": crypto_receipt,
                }
                db_manager.update_challenge(address, challenge["challengeId"], update)
                
                # Rename to .validated
                validated_path = solution_path.replace('.json', '.validated')
                os.rename(solution_path, validated_path)
                
                print(f"  ✓ {challenge['challengeId'][:10]}... - Successfully validated!")
                return True
            else:
                print(f"  ⚠ {challenge['challengeId'][:10]}... - Submitted but no crypto_receipt")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"  ✗ {challenge['challengeId'][:10]}... - Request error: {e}")
            return False
        except Exception as e:
            print(f"  ✗ {challenge['challengeId'][:10]}... - Error: {e}")
            return False
    
    # Submit with thread pool
    successful = 0
    failed = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(submit_one, addr, c, path): (addr, c) 
                   for addr, c, path in unsubmitted_tasks}
        
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                successful += 1
            else:
                failed += 1
    
    print(f"\nRetry complete: {successful} successful, {failed} failed")
    print("Saving database...")
    db_manager.save_to_disk()
    print("Done.")


def display_mining_summary(db_manager):
    """Display mining summary with earnings per address on startup."""
    print("\n" + "="*70)
    print("MINING SUMMARY")
    print("="*70)
    
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
    
    addresses = db_manager.get_addresses()
    if not addresses:
        print("No addresses found.")
        print("="*70 + "\n")
        return
    
    print(f"Addresses: {len(addresses)} | Days with rates: {len(work_to_star_rates)}\n")
    
    grand_total_star = 0
    address_summaries = []
    
    for address in addresses:
        challenges = db_manager.get_challenge_queue(address)
        
        # Count validated challenges by day
        validated_by_day = {}
        total_validated = 0
        
        for c in challenges:
            if c.get("status") == "validated":
                campaign_day = c.get("campaignDay")
                if campaign_day is not None:
                    validated_by_day[campaign_day] = validated_by_day.get(campaign_day, 0) + 1
                    total_validated += 1
        
        if total_validated == 0:
            continue
        
        # Calculate earnings
        address_total_star = 0
        
        for day in validated_by_day.keys():
            count = validated_by_day[day]
            # Day is 1-indexed, list is 0-indexed
            if day - 1 < len(work_to_star_rates):
                star_per_solution = work_to_star_rates[day - 1]
                day_star = count * star_per_solution
                address_total_star += day_star
        
        address_night = address_total_star / 1_000_000
        short_addr = f"{address[:6]}...{address[-4:]}"
        address_summaries.append((short_addr, total_validated, address_night, address_total_star))
        grand_total_star += address_total_star
    
    # Print table
    print(f"{'Address':<16} {'Solutions':>10} {'$NIGHT':>15}")
    print("─" * 70)
    for short_addr, count, night, star in address_summaries:
        print(f"{short_addr:<16} {count:>10} {night:>15.6f}")
    
    # Grand total
    grand_total_night = grand_total_star / 1_000_000
    print("─" * 70)
    print(f"{'TOTAL':<16} {sum(s[1] for s in address_summaries):>10} {grand_total_night:>15.6f}")
    print(f"\n{grand_total_star:,} $STAR")
    print("="*70 + "\n")


def run_orchestrator(args):
    """Starts and manages the TUI and all worker threads."""
    logging.info("Starting orchestrator TUI...")
    ensure_directories()  # Create necessary directories
    db_manager = DatabaseManager()
    
    # Display mining summary before starting TUI
    display_mining_summary(db_manager)

    worker_functions = {
        "fetcher": fetcher_worker,
        "solver": solver_worker,
        "saver": saver_worker,
    }

    worker_args = {
        "solve_interval": args.solve_interval,
        "save_interval": args.save_interval,
        "max_solvers": args.max_solvers,
        "fetch_interval_minutes": args.fetch_interval,
    }

    app = OrchestratorTUI(
        db_manager=db_manager,
        worker_functions=worker_functions,
        worker_args=worker_args,
    )
    app.run()
    logging.info("Orchestrator shut down.")


def main():
    parser = argparse.ArgumentParser(
        description="Challenge orchestrator for Midnight scavenger hunt."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Initialize or update the database from JSON files."
    )
    init_parser.add_argument("files", nargs="+", help="List of JSON files to import.")

    run_parser = subparsers.add_parser("run", help="Run the orchestrator with TUI.")
    run_parser.add_argument(
        "--max-solvers",
        type=int,
        default=4,  # A sensible default
        help="Maximum number of concurrent solver processes to run (default: 4).",
    )
    run_parser.add_argument(
        "--solve-interval",
        type=int,
        default=DEFAULT_SOLVE_INTERVAL,
        help=f"Interval in seconds for the solver to check for challenges (default: {DEFAULT_SOLVE_INTERVAL}).",
    )
    run_parser.add_argument(
        "--save-interval",
        type=int,
        default=DEFAULT_SAVE_INTERVAL,
        help=f"Interval in seconds for saving the database to disk (default: {DEFAULT_SAVE_INTERVAL}).",
    )
    run_parser.add_argument(
        "--fetch-interval",
        type=int,
        default=None,
        help="Interval in minutes to fetch new challenges from API. If not set, uses smart timing (5 minutes after each hour).",
    )

    # Separate subcommand for retrying submissions
    retry_parser = subparsers.add_parser(
        "retry-submissions",
        help="Retry submitting all unsubmitted solutions (no mining, just submission)."
    )
    retry_parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum number of concurrent submission workers (default: 4).",
    )

    args = parser.parse_args()

    setup_logging()

    if args.command == "init":
        init_db(args.files)
    elif args.command == "run":
        if not os.path.exists(DB_FILE):
            print("Database file not found. Please run the 'init' command first.")
            logging.critical("Database file not found. Aborting run.")
            os._exit(1)  # Exit immediately without traceback
        run_orchestrator(args)
    elif args.command == "retry-submissions":
        if not os.path.exists(DB_FILE):
            print("Database file not found. Please run the 'init' command first.")
            logging.critical("Database file not found. Aborting retry.")
            os._exit(1)
        db_manager = DatabaseManager()
        retry_submissions(db_manager, args.max_workers)


if __name__ == "__main__":
    main()
