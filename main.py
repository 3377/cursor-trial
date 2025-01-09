import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from secrets import randbelow, token_urlsafe

from colorama import Fore, Style, init
from requests import session
from seleniumbase import SB


TIMEOUT_SECONDS = 60
RETRY_INTERVAL = 2
MAX_ATTEMPTS = 3
BASE_URL = "https://authenticator.cursor.sh"
BURNER_EMAIL_URL = "https://burner.kiwi/"

def log_message(message, level="info"):
    """Unified logging function with color support"""
    colors = {
        "info": Fore.BLUE,
        "success": Fore.GREEN,
        "error": Fore.RED,
        "warning": Fore.YELLOW
    }
    symbol = {"info": "*", "success": "+", "error": "!", "warning": "!"}
    print(f"{color(f'[{symbol[level]}]', colors[level])} {message}")

def color(text, color_code=Fore.CYAN):
    """Colorize text with the specified color code"""
    return f"{color_code}{text}{Style.RESET_ALL}"

def solve_captcha(sb):
    """Try to complete the security check by waiting for the specific wrapper div"""
    # Wait for case 1 specifically - the wrapper with min-content width style
    wrapper = 'div.rt-Box[style*="--width: min-content"]'
    sb.wait_for_element(f"{wrapper} div#cf-turnstile", timeout=60)

    log_message("Waiting for captcha to be solved...")
    while True:
        sb.wait(randbelow(1000) / 1000)
        sb.cdp.mouse_click(f"{wrapper} #cf-turnstile")
        try:
            sb.wait_for_element_not_visible(f"{wrapper} div#cf-turnstile", timeout=randbelow(5))
            break
        except Exception as _:
            try:
                if sb.assert_text("Can‘t verify the user is human. Please try again."):
                    return False
                break
            except Exception as _:
                continue
    log_message("Captcha solved!", "success")
    return True

def enter_code(sb, code):
    """Type in the 6-digit code"""
    box = lambda n: f"body > div.radix-themes > div > div > div:nth-child(2) > div > form > div > div > div > div:nth-child({n}) > input"
    for i, digit in enumerate(code):
        sb.send_keys(box(i + 1), digit)

def get_token(sb, max_attempts=MAX_ATTEMPTS, retry_interval=RETRY_INTERVAL):
    """Try to get the Cursor session token with retries"""
    log_message("Getting session token...")
    
    for attempt in range(max_attempts):
        try:
            for cookie in sb.get_cookies():
                if cookie.get("name") == "WorkosCursorSessionToken":
                    token = cookie["value"].split("%3A%3A")[1]
                    log_message("Got session token!", "success")
                    return token
            
            if attempt < max_attempts - 1:
                log_message(f"Attempt {attempt + 1} failed, retrying in {retry_interval}s...", "warning")
                sb.sleep(retry_interval)
            else:
                log_message(f"Failed to get token after {max_attempts} attempts", "error")
                
        except Exception as e:
            log_message(f"Cookie error: {e}", "error")
            if attempt < max_attempts - 1:
                log_message(f"Retrying in {retry_interval}s...", "warning")
                sb.sleep(retry_interval)
    
    return None

def update_auth(email=None, access_token=None, refresh_token=None):
    """Update Cursor login info in the database
    Special thanks to https://github.com/chengazhen/cursor-auto-free for the original implementation"""
    appdata = os.getenv("APPDATA")
    if not appdata:
        log_message("APPDATA environment variable not set", "error")
        return False
        
    db_path = os.path.join(
        appdata, "Cursor", "User", "globalStorage", "state.vscdb"
    )
    
    # Build update list
    updates = [("cursorAuth/cachedSignUpType", "Auth_0")]
    if email is not None:
        updates.append(("cursorAuth/cachedEmail", email))
    if access_token is not None:
        updates.append(("cursorAuth/accessToken", access_token))
    if refresh_token is not None:
        updates.append(("cursorAuth/refreshToken", refresh_token))

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for key, value in updates:
            # Check if key exists
            cursor.execute("SELECT COUNT(*) FROM itemTable WHERE key = ?", (key,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO itemTable (key, value) VALUES (?, ?)", (key, value))
            else:
                cursor.execute("UPDATE itemTable SET value = ? WHERE key = ?", (value, key))

        conn.commit()
        return True
    except sqlite3.Error as e:
        log_message(f"Database error: {e}", "error")
        return False
    finally:
        if conn:
            conn.close()

def reset_machine():
    """Try to change the machine ID and close Cursor"""
    try:
        subprocess.run([
            'powershell.exe',
            '-WindowStyle', 'Hidden',
            '-ExecutionPolicy', 'Bypass',
            '-File', 'reset.ps1'
        ], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Could not change machine ID or close Cursor: {e}", "error")
        return False

def reset_device():
    """Try to change the device tracking ID
    Special thanks to https://github.com/yuaotian/go-cursor-help for the brilliant solution"""
    appdata = os.getenv("APPDATA")
    if not appdata:
        log_message("APPDATA environment variable not set", "error")
        return False
        
    storage_path = os.path.join(
        appdata, "Cursor", "User", "globalStorage", "storage.json"
    )
    
    try:
        # Read current settings
        with open(storage_path, 'r') as f:
            config = json.load(f)
        
        # Make new IDs
        config['telemetry.devDeviceId'] = f"{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:12]}"
        config['telemetry.macMachineId'] = str(uuid.uuid4())
        config['telemetry.machineId'] = uuid.uuid4().hex + uuid.uuid4().hex
        config['telemetry.sqmId'] = "{" + str(uuid.uuid4()).upper() + "}"
        
        # Save new settings
        with open(storage_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        return True
    except FileNotFoundError:
        log_message(f"Could not find settings file at: {storage_path}", "error")
        return False
    except json.JSONDecodeError:
        log_message("Settings file has wrong format", "error")
        return False
    except PermissionError:
        log_message("No permission to change settings file", "error")
        return False
    except Exception as e:
        log_message(f"Could not change device ID: {e}", "error")
        return False

def get_temp_email(session):
    """Get a temporary email address from burner.kiwi
    Returns: email address string or None if failed"""
    mail_content = session.get("https://burner.kiwi/").text
    email_match = re.search(r'<h1 class="inbox-address">([^<]+)</h1>', mail_content)
    if not email_match:
        log_message("Failed to generate temp mail", "error")
        return None
    return email_match.group(1)

def wait_for_verification_code(session):
    """Wait for and extract verification code from burner.kiwi email
    Returns: 6-digit verification code or None if failed"""
    # Wait for email to arrive
    while True:
        mail_match = re.search(r'<a class="sidebar-email " href="([^"]*)"', session.get("https://burner.kiwi/").text)
        if mail_match:
            break
        time.sleep(1)
    
    # Extract verification code
    email_content = session.get("https://burner.kiwi/" + mail_match.group(1)).text
    code_match = re.search(r'is (\d{6}\b)', email_content)
    if not code_match:
        log_message("Failed to get verification code", "error")
        return None
    return code_match.group(1)

def register():
    """Create a new Cursor account with temporary email and automated verification"""
    init()  # Initialize colorama for colored console output
    
    with SB(uc=True, test=True, disable_csp=True, headless=True, extension_dir="turnstile") as sb:
        log_message("Initializing new account registration process...")
        
        # Email setup
        email_session = session()
        log_message(f"Generating temporary email address from {color('burner.kiwi', Fore.YELLOW)}...")
        if not (email := get_temp_email(email_session)):
            return

        # Registration setup  
        credentials = {
            "name": "John",
            "last_name": "Doe",
            "password": token_urlsafe(24),
            "email": email
        }
        
        register_url = f"{BASE_URL}/sign-up/password?first_name={credentials['name']}&last_name={credentials['last_name']}&email={credentials['email']}"
        
        log_message(f"Navigating to registration page with email: {color(email)}")
        sb.activate_cdp_mode(register_url)

        # Complete registration form
        log_message(f"Filling registration form with {color('credentials', Fore.YELLOW)}...")
        sb.send_keys("input[name='password']", credentials['password'])
        sb.uc_click("button[value='sign-up']")

        # Handle first Cloudflare Turnstile verification
        log_message(f"Initiating first {color('Cloudflare', Fore.YELLOW)} security verification...")
        if not solve_captcha(sb):
            log_message("First security verification failed, aborting...", "error")
            return

        # Get verification code from email
        log_message(f"Checking {color('burner.kiwi', Fore.YELLOW)} inbox...")
        verification_code = wait_for_verification_code(email_session)
        if not verification_code:
            return

        log_message(f"Verification code received: {color(verification_code)}")
        enter_code(sb, verification_code)

        # Handle second Cloudflare Turnstile verification
        log_message(f"Initiating second {color('Cloudflare', Fore.YELLOW)} security verification...")
        if not solve_captcha(sb):
            log_message("Second security verification failed, aborting...", "error")
            return

        # Verify successful registration
        log_message("Verifying successful registration...")
        start_time = time.time()
        while sb.get_current_url() != "https://www.cursor.com/":
            if time.time() - start_time > 60:
                log_message("Registration verification timed out after 60 seconds", "error")
                return
            sb.sleep(1)
        log_message(f"Account successfully created! Credentials: {color(f"{credentials['email']}:{credentials['password']}")}", "success")

        # Retrieve and store authentication tokens
        session_token = get_token(sb)
        if session_token:
            log_message(f"Authentication token retrieved: {color(f'{session_token[:10]}...')}", "success")
        
        # Update local Cursor authentication
        log_message(f"Updating local {color('Cursor', Fore.YELLOW)} authentication...")
        if update_auth(credentials['email'], session_token, session_token):
            log_message("Local authentication updated", "success")
        else:
            log_message("Failed to update local authentication", "error")

        # Reset machine identification
        log_message(f"Initiating {color('machine ID', Fore.YELLOW)} reset...")
        if reset_machine():
            log_message("Machine ID reset and Cursor shutdown completed", "success")
        else:
            log_message("Failed to reset machine ID or shutdown Cursor", "error")

        # Reset device identification
        log_message(f"Initiating {color('device ID', Fore.YELLOW)} reset...")
        if reset_device():
            log_message("Device ID reset completed", "success")
        else:
            log_message("Failed to reset device ID", "error")

if __name__ == "__main__":
    register()

