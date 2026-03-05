#!/bin/bash
# Install the Automator Quick Action for the Option+Shift+W shortcut.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKFLOW_DIR="$HOME/Library/Services/Wispr Unleashed.workflow/Contents"

echo "Setting up Wispr Unleashed keyboard shortcut..."

# Remove old workflow if present
rm -rf "$HOME/Library/Services/Wispr Unleashed.workflow"
mkdir -p "$WORKFLOW_DIR"

# Create Info.plist (required for macOS to detect the workflow)
python3 -c "
import plistlib

info = {
    'CFBundleName': 'Wispr Unleashed',
    'CFBundleIdentifier': 'com.wispr-unleashed.shortcut',
    'CFBundleVersion': '1.0',
    'CFBundleShortVersionString': '1.0',
    'CFBundleInfoDictionaryVersion': '6.0',
    'CFBundlePackageType': 'BNDL',
    'NSServices': [{
        'NSMenuItem': {'default': 'Wispr Unleashed'},
        'NSMessage': 'runWorkflowAsService',
        'NSRequiredContext': {},
        'NSSendTypes': [],
        'NSReturnTypes': [],
    }],
}

with open('$WORKFLOW_DIR/Info.plist', 'wb') as f:
    plistlib.dump(info, f)
"

# Create the Automator workflow document
python3 -c "
import plistlib, uuid

action_uuid = str(uuid.uuid4()).upper()

wflow = {
    'AMApplicationBuild': '523',
    'AMApplicationVersion': '2.10',
    'AMDocumentVersion': '2',
    'actions': [{
        'action': {
            'AMAccepts': {'Container': 'List', 'Optional': True, 'Types': ['com.apple.cocoa.string']},
            'AMActionVersion': '2.0.3',
            'AMApplication': ['Automator'],
            'AMBundleIdentifier': 'com.apple.RunShellScript',
            'AMCategory': 'AMCategoryUtilities',
            'AMIconName': 'RunShellScript',
            'AMKeywords': [],
            'AMName': 'Run Shell Script',
            'AMParameters': {
                'COMMAND_STRING': '$SCRIPT_DIR/toggle.sh',
                'CheckedForUserDefaultShell': True,
                'inputMethod': 0,
                'shell': '/bin/bash',
                'source': '',
            },
            'AMProvides': {'Container': 'List', 'Types': ['com.apple.cocoa.string']},
            'AMTag': 'AMTagUtilities',
            'ActionBundlePath': '/System/Library/Automator/Run Shell Script.action',
            'ActionName': 'Run Shell Script',
            'ActionParameters': {
                'COMMAND_STRING': '$SCRIPT_DIR/toggle.sh',
                'CheckedForUserDefaultShell': True,
                'inputMethod': 0,
                'shell': '/bin/bash',
                'source': '',
            },
            'BundleIdentifier': 'com.apple.RunShellScript',
            'CFBundleVersion': '2.0.3',
            'CanShowSelectedItemsWhenRun': False,
            'CanShowWhenRun': True,
            'Category': ['AMCategoryUtilities'],
            'Class Name': 'RunShellScriptAction',
            'InputUUID': str(uuid.uuid4()).upper(),
            'Keywords': [],
            'OutputUUID': str(uuid.uuid4()).upper(),
            'UUID': action_uuid,
            'UnlocalizedApplications': ['Automator'],
            'arguments': {
                '0': {'default value': '', 'name': 'COMMAND_STRING', 'required': '0', 'type': '0', 'uuid': '0'},
                '1': {'default value': '/bin/sh', 'name': 'shell', 'required': '0', 'type': '0', 'uuid': '1'},
                '2': {'default value': '0', 'name': 'inputMethod', 'required': '0', 'type': '0', 'uuid': '2'},
                '3': {'default value': '', 'name': 'source', 'required': '0', 'type': '0', 'uuid': '3'},
                '4': {'default value': True, 'name': 'CheckedForUserDefaultShell', 'required': '0', 'type': '0', 'uuid': '4'},
            },
            'isViewVisible': True,
            'location': '449.500000:620.000000',
            'nibPath': '/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib',
        }
    }],
    'connectors': {},
    'workflowMetaData': {
        'applicationBundleIDsByPath': {},
        'applicationPaths': [],
        'inputTypeIdentifier': 'com.apple.Automator.nothing',
        'outputTypeIdentifier': 'com.apple.Automator.nothing',
        'presentationMode': 15,
        'processesInput': 0,
        'serviceApplicationGroupName': 'General',
        'serviceApplicationPath': '/System/Applications/Utilities/Automator.app',
        'serviceInputTypeIdentifier': 'com.apple.Automator.nothing',
        'serviceOutputTypeIdentifier': 'com.apple.Automator.nothing',
        'serviceProcessesInput': 0,
        'systemImageName': 'NSTouchBarRecord',
        'useAutomaticInputType': False,
        'workflowTypeIdentifier': 'com.apple.Automator.servicesMenu',
    },
}

with open('$WORKFLOW_DIR/document.wflow', 'wb') as f:
    plistlib.dump(wflow, f)
"

# Force macOS to re-scan services
/System/Library/CoreServices/pbs -flush 2>/dev/null || true
killall -u "$USER" pbs 2>/dev/null || true

echo "✓ Automator Quick Action installed"
echo ""
echo "Now assign the keyboard shortcut:"
echo "  1. Open System Settings → Keyboard → Keyboard Shortcuts → Services"
echo "  2. Look for 'General' section (you may need to scroll or close and reopen)"
echo "  3. Find 'Wispr Unleashed' and click 'Add Shortcut'"
echo "  4. Press Option+Shift+W"
echo ""
echo "Opening System Settings for you..."
open "x-apple.systempreferences:com.apple.Keyboard-Settings.extension"
