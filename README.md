# Cursor Automation Testing Tool
*Currently works only on Windows*
*Tested on Cursor version 0.44.11*
*Tested on Chrome version 131.0.6778.205*

Inspired by:
- [go-cursor-help](https://github.com/yuaotian/go-cursor-help)
- [cursor-auto-free](https://github.com/chengazhen/cursor-auto-free)
- [gpt-cursor-auto](https://github.com/hmhm2022/gpt-cursor-auto)

## What it does
1. Account Creation
   - Creates temporary email addresses
   - Handles security verifications
   - Helps with account registration
   - Manages verification codes

2. System Configuration
   - Changes machine GUID
   - Updates telemetry device ID
   - Sets up authentication data

## What you need
- Windows computer
- Python (tested on 3.12.7)
- Chrome browser (tested on 131.0.6778.205)
- Python packages needed:
  - seleniumbase~=4.33.0 (for browser automation)
  - tempmail-python~=2.3.3 (for temporary email services)
  - colorama~=0.4.0 (for colored console output)

## How to use
1. Get the code
   ```bash
   git clone https://github.com/alihakanarslan/cursor-trial.git
   ```

2. Go to the folder
   ```bash
   cd cursor-trial
   ```

3. Install needed packages
   ```bash
   pip install -r requirements.txt
   ```

4. Start the program
   ```bash
   python main.py
   ```

## Important notice
This is a learning project provided without any warranties. The author is not responsible for how you use it.

- Made for learning purposes only
- Please follow Cursor's terms of service
- Use at your own risk
