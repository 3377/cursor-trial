from seleniumbase import SB
from tempmail import EMail
from secrets import token_urlsafe
from colorama import init, Fore, Style
import re
import subprocess
import sqlite3
import os
import uuid
import json

def log_info(message, *values):
    """Show an info message with optional highlighted values"""
    value_str = ''.join(f"{Fore.CYAN}{v}{Style.RESET_ALL}" for v in values)
    print(f"{Fore.BLUE}[*]{Style.RESET_ALL} {message}{value_str}")

def log_success(message, *values):
    """Show a success message with optional highlighted values"""
    value_str = ''.join(f"{Fore.CYAN}{v}{Style.RESET_ALL}" for v in values)
    print(f"{Fore.GREEN}[+]{Style.RESET_ALL} {message}{value_str}")

def solve_turnstile(sb):
    """Try to complete the security check"""
    sb.cdp.assert_element_not_visible("div[aria-hidden='true'] #cf-turnstile")
    sb.wait(0.5)
    sb.cdp.mouse_click("#cf-turnstile")

def enter_verification_code(sb, code):
    """Type in the 6-digit code"""
    box = lambda n: f"body > div.radix-themes > div > div > div:nth-child(2) > div > form > div > div > div > div:nth-child({n}) > input"
    for i, digit in enumerate(code):
        sb.send_keys(box(i + 1), digit)

def extract_verification_code(message_body):
    """Find the 6-digit code in the email"""
    return re.search(r'<div style="[^"]*?">\s*?(\d{6})\s*?</div>', message_body).group(1)

def get_cursor_session_token(sb, max_attempts=3, retry_interval=2):
    """Try to get the Cursor session token with retries"""
    log_info("Getting session token...")
    attempts = 0

    while attempts < max_attempts:
        try:
            # Get cookies directly from the browser context instead of driver
            cookies = sb.get_cookies()
            
            # Look for the WorkosCursorSessionToken
            for cookie in cookies:
                if cookie.get("name") == "WorkosCursorSessionToken":
                    token = cookie["value"].split("%3A%3A")[1]
                    log_success("Got session token!")
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

def update_cursor_auth(email=None, access_token=None, refresh_token=None):
    """Update Cursor login info in the database
    Special thanks to https://github.com/chengazhen/cursor-auto-free for the original implementation"""
    db_path = os.path.join(
        os.getenv("APPDATA"), "Cursor", "User", "globalStorage", "state.vscdb"
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

def change_machine_guid_and_close():
    """Try to change the machine ID and close Cursor"""
    try:
        subprocess.call(['reset.bat'])
        return True
    except subprocess.CalledProcessError as e:
        print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not change machine ID or close Cursor: {e}")
        return False

def change_telemetry_device_id():
    """Try to change the device tracking ID
    Special thanks to https://github.com/yuaotian/go-cursor-help for the brilliant solution"""
    storage_path = os.path.join(
        os.getenv("APPDATA"), "Cursor", "User", "globalStorage", "storage.json"
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

def register_account():
    """Try to make a new account"""
    init()  # Start colorama
    
    with SB(uc=True, test=True, disable_csp=True, extension_dir="turnstile", headless=True) as sb:
        log_info("Starting to make a new account...")
        
        # Set up account info
        name = "John"
        last_name = "Doe"
        email = EMail()
        password = token_urlsafe(24)
        url = f"https://authenticator.cursor.sh/sign-up/password?first_name={name}&last_name={last_name}&email={email}"
        
        log_info("Using email: ", email.address)

        # Fill out the form
        log_info("Going to signup page...")
        sb.activate_cdp_mode(url)
        sb.send_keys("input[name='password']", password)
        log_info("Sending form...")
        sb.uc_click("button[value='sign-up']")

        # First security check
        log_info("Waiting for first security check...")
        solve_turnstile(sb)

        # Check email
        log_info("Waiting for email...")
        message_body = email.wait_for_message().body
        six_digit_number = extract_verification_code(message_body)
        log_info("Got code: ", six_digit_number)
        
        # Put in the code
        log_info("Typing code...")
        enter_verification_code(sb, six_digit_number)

        # Second security check
        log_info("Waiting for second security check...")
        solve_turnstile(sb)

        # Check if it worked
        log_info("Checking if signup worked...")
        sb.assert_text("The AI Code Editor")
        log_success("Made new account! Login info: ", f"{email.address}:{password}")

        # Get session token
        session_token = get_cursor_session_token(sb)
        if session_token:
            log_success("Got session token: ", session_token)
        
        # Set up Cursor login
        log_info("Setting up Cursor login...")
        if update_cursor_auth(email.address, session_token, session_token):
            log_success("Login info saved!")
        else:
            print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not save login info")

        # Change IDs and close
        log_info("Changing IDs and closing Cursor...")
        if change_machine_guid_and_close():
            log_success("Changed IDs and closed Cursor!")
        else:
            print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not change IDs or close Cursor")

        # Change device ID
        log_info("Changing device ID...")
        if change_telemetry_device_id():
            log_success("Changed device ID!")
        else:
            print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not change device ID")

if __name__ == "__main__":
    register_account()

