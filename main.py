import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from secrets import randbelow, token_urlsafe

from colorama import Fore, Style, init
from seleniumbase import SB
from requests import session


def color(text, color_code=Fore.CYAN):
    """Colorize text with the specified color code"""
    return f"{color_code}{text}{Style.RESET_ALL}"

def info(message):
    """Show an info message"""
    print(f"{color('[*]', Fore.BLUE)} {message}")

def success(message):
    """Show a success message"""
    print(f"{color('[+]', Fore.GREEN)} {message}")

def error(message):
    """Show an error message"""
    print(f"{color('[!]', Fore.RED)} {message}")

def solve_captcha(sb):
    """Try to complete the security check by waiting for the specific wrapper div"""
    # Wait for case 1 specifically - the wrapper with min-content width style
    wrapper = 'div.rt-Box[style*="--width: min-content"]'
    sb.wait_for_element(f"{wrapper} div#cf-turnstile", timeout=60)

    info("Waiting for captcha to be solved...")
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
    success("Captcha solved!")
    return True

def enter_code(sb, code):
    """Type in the 6-digit code"""
    box = lambda n: f"body > div.radix-themes > div > div > div:nth-child(2) > div > form > div > div > div > div:nth-child({n}) > input"
    for i, digit in enumerate(code):
        sb.send_keys(box(i + 1), digit)

def get_token(sb, max_attempts=3, retry_interval=2):
    """Try to get the Cursor session token with retries"""
    info("Getting session token...")
    attempts = 0

    while attempts < max_attempts:
        try:
            # Get cookies directly from the browser context instead of driver
            cookies = sb.get_cookies()
            
            # Look for the WorkosCursorSessionToken
            for cookie in cookies:
                if cookie.get("name") == "WorkosCursorSessionToken":
                    token = cookie["value"].split("%3A%3A")[1]
                    success("Got session token!")
                    return token

            attempts += 1
            if attempts < max_attempts:
                print(f"{Fore.YELLOW}[!]{Style.RESET_ALL} Attempt {attempts} failed, retrying in {retry_interval}s...")
                sb.sleep(retry_interval)
            else:
                print(f"{Fore.RED}[!]{Style.RESET_ALL} Failed to get token after {max_attempts} attempts")

        except Exception as e:
            attempts += 1
            print(f"{Fore.RED}[!]{Style.RESET_ALL} Cookie error: {e}")
            if attempts < max_attempts:
                print(f"{Fore.YELLOW}[!]{Style.RESET_ALL} Retrying in {retry_interval}s...")
                sb.sleep(retry_interval)

    return None

def update_auth(email=None, access_token=None, refresh_token=None):
    """Update Cursor login info in the database
    Special thanks to https://github.com/chengazhen/cursor-auto-free for the original implementation"""
    appdata = os.getenv("APPDATA")
    if not appdata:
        error("APPDATA environment variable not set")
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
        print(f"{Fore.RED}[!]{Style.RESET_ALL} Database error: {e}")
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
        print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not change machine ID or close Cursor: {e}")
        return False

def reset_device():
    """Try to change the device tracking ID
    Special thanks to https://github.com/yuaotian/go-cursor-help for the brilliant solution"""
    appdata = os.getenv("APPDATA")
    if not appdata:
        error("APPDATA environment variable not set")
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
        print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not find settings file at: {storage_path}")
        return False
    except json.JSONDecodeError:
        print(f"{Fore.RED}[!]{Style.RESET_ALL} Settings file has wrong format")
        return False
    except PermissionError:
        print(f"{Fore.RED}[!]{Style.RESET_ALL} No permission to change settings file")
        return False
    except Exception as e:
        print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not change device ID: {e}")
        return False

def get_temp_email(session):
    """Get a temporary email address from burner.kiwi
    Returns: email address string or None if failed"""
    mail_content = session.get("https://burner.kiwi/").text
    email_match = re.search(r'<h1 class="inbox-address">([^<]+)</h1>', mail_content)
    if not email_match:
        error("Failed to generate temp mail")
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
        error("Failed to get verification code")
        return None
    return code_match.group(1)

def register():
    """Create a new Cursor account with temporary email and automated verification"""
    init()  # Initialize colorama for colored console output
    
    with SB(uc=True, test=True, disable_csp=True, headless=True, extension_dir="turnstile") as sb:
        info("Initializing new account registration process...")

        # Set up email session and get temporary address
        email_session = session()
        info(f"Generating temporary email address from {color('burner.kiwi', Fore.YELLOW)}...")
        email = get_temp_email(email_session)
        if not email:
            return

        # Set up registration details
        name = "John"
        last_name = "Doe"
        password = token_urlsafe(24)
        register_url = f"https://authenticator.cursor.sh/sign-up/password?first_name={name}&last_name={last_name}&email={email}"

        info(f"Navigating to registration page with email: {color(email)}")
        sb.activate_cdp_mode(register_url)

        # Complete registration form
        info(f"Filling registration form with {color('credentials', Fore.YELLOW)}...")
        sb.send_keys("input[name='password']", password)
        sb.uc_click("button[value='sign-up']")

        # Handle first Cloudflare Turnstile verification
        info(f"Initiating first {color('Cloudflare', Fore.YELLOW)} security verification...")
        if not solve_captcha(sb):
            error("First security verification failed, aborting...")
            return

        # Get verification code from email
        info(f"Checking {color('burner.kiwi', Fore.YELLOW)} inbox...")
        verification_code = wait_for_verification_code(email_session)
        if not verification_code:
            return

        info(f"Verification code received: {color(verification_code)}")
        enter_code(sb, verification_code)

        # Handle second Cloudflare Turnstile verification
        info(f"Initiating second {color('Cloudflare', Fore.YELLOW)} security verification...")
        if not solve_captcha(sb):
            error("Second security verification failed, aborting...")
            return

        # Verify successful registration
        info("Verifying successful registration...")
        start_time = time.time()
        while sb.get_current_url() != "https://www.cursor.com/":
            if time.time() - start_time > 60:
                error("Registration verification timed out after 60 seconds")
                return
            sb.sleep(1)
        success(f"Account successfully created! Credentials: {color(f'{email}:{password}')}")

        # Retrieve and store authentication tokens
        session_token = get_token(sb)
        if session_token:
            success(f"Authentication token retrieved: {color(f'{session_token[:10]}...')}")
        
        # Update local Cursor authentication
        info(f"Updating local {color('Cursor', Fore.YELLOW)} authentication...")
        if update_auth(email, session_token, session_token):
            success("Local authentication updated")
        else:
            error("Failed to update local authentication")

        # Reset machine identification
        info(f"Initiating {color('machine ID', Fore.YELLOW)} reset...")
        if reset_machine():
            success("Machine ID reset and Cursor shutdown completed")
        else:
            error("Failed to reset machine ID or shutdown Cursor")

        # Reset device identification
        info(f"Initiating {color('device ID', Fore.YELLOW)} reset...")
        if reset_device():
            success("Device ID reset completed")
        else:
            error("Failed to reset device ID")

if __name__ == "__main__":
    register()

