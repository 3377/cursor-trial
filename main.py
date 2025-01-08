from seleniumbase import SB
from tempmail import EMail
from secrets import token_urlsafe, randbelow
from colorama import init, Fore, Style
import re
import subprocess
import sqlite3
import os
import uuid
import json
import time

def info(message, *values):
    """Show an info message with optional highlighted values"""
    value_str = ''.join(f"{Fore.CYAN}{v}{Style.RESET_ALL}" for v in values)
    print(f"{Fore.BLUE}[*]{Style.RESET_ALL} {message}{value_str}")

def success(message, *values):
    """Show a success message with optional highlighted values"""
    value_str = ''.join(f"{Fore.CYAN}{v}{Style.RESET_ALL}" for v in values)
    print(f"{Fore.GREEN}[+]{Style.RESET_ALL} {message}{value_str}")


def error(message, *values):
    """Show an error message with optional highlighted values"""
    value_str = ''.join(f"{Fore.CYAN}{v}{Style.RESET_ALL}" for v in values)
    print(f"{Fore.RED}[!]{Style.RESET_ALL} {message}{value_str}")

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

def get_code(message_body):
    """Find the 6-digit code in the email"""
    return re.search(r'<div style="[^"]*?">\s*?(\d{6})\s*?</div>', message_body).group(1)

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

def register():
    """Try to make a new account"""
    init()  # Start colorama
    
    with SB(uc=True, test=True, disable_csp=True, headless=True, extension_dir="turnstile") as sb:
        info("Starting to make a new account...")
        
        # Set up account info
        name = "John"
        last_name = "Doe"
        email = EMail()
        password = token_urlsafe(24)
        url = f"https://authenticator.cursor.sh/sign-up/password?first_name={name}&last_name={last_name}&email={email}"
        
        info("Using email: ", email.address)

        # Fill out the form
        info("Going to signup page...")
        sb.activate_cdp_mode(url)
        sb.send_keys("input[name='password']", password)
        info("Sending form...")
        sb.uc_click("button[value='sign-up']")

        # First security check
        info("Waiting for first security check...")
        if not solve_captcha(sb):
            error("Failed to solve first security check, exiting...")
            return

        # Check email
        info("Waiting for email...")
        message_body = email.wait_for_message().body
        six_digit_number = get_code(message_body)
        info("Got code: ", six_digit_number)
        
        # Put in the code
        info("Typing code...")
        enter_code(sb, six_digit_number)

        # Second security check
        info("Waiting for second security check...")
        if not solve_captcha(sb):
            error("Failed to solve second security check, exiting...")
            return

        # Check if it worked
        info("Checking if signup worked...")
        start_time = time.time()
        while sb.get_current_url() != "https://www.cursor.com/":
            if time.time() - start_time > 60:  # 60 second timeout
                error("Signup verification timed out after 60 seconds, exiting...")
                return
            sb.sleep(1)
        success("Made new account! Login info: ", f"{email.address}:{password}")

        # Get session token
        session_token = get_token(sb)
        if session_token:
            success("Got session token: ", session_token)
        
        # Set up Cursor login
        info("Setting up Cursor login...")
        if update_auth(email.address, session_token, session_token):
            success("Login info saved!")
        else:
            print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not save login info")

        # Change IDs and close
        info("Changing IDs and closing Cursor...")
        if reset_machine():
            success("Changed IDs and closed Cursor!")
        else:
            print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not change IDs or close Cursor")

        # Change device ID
        info("Changing device ID...")
        if reset_device():
            success("Changed device ID!")
        else:
            print(f"{Fore.RED}[!]{Style.RESET_ALL} Could not change device ID")

if __name__ == "__main__":
    register()

