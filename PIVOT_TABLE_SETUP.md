# Automatic Pivot Table Date Filter Setup

## Overview

This guide provides step-by-step instructions to automatically update the pivot table in your "Óránkénti jelentés" (Hourly Report) sheet to always display data from the latest date in your Trading212 dataset.

## What This Does

- Automatically finds the latest date in your **RawData** sheet
- Updates the date filter in the **Óránkénti jelentés** pivot table
- Runs automatically every 5 minutes
- Can also be triggered manually whenever needed

## Prerequisites

- Your Trading212 Google Sheet with:
  - **RawData** sheet containing trade data with a "Date" column in column A
  - **Óránkénti jelentés** sheet with a pivot table that has a date filter
- Access to Google Apps Script

## Installation Steps

### Step 1: Open Your Google Sheet
1. Open your Trading212 Google Sheet in your browser

### Step 2: Access Google Apps Script
1. Click on **Extensions** menu (top menu bar)
2. Select **Apps Script**
3. A new tab will open with the Apps Script editor

### Step 3: Delete Existing Code
1. If there's any existing code in the editor, select all (Ctrl+A) and delete it

### Step 4: Copy the Script
1. Open the file `pivot_table_auto_filter.gs` from this repository
2. Copy the entire content
3. Paste it into the Google Apps Script editor

### Step 5: Save the Project
1. Click the **Save** button (or press Ctrl+S)
2. Give your project a name (e.g., "Trading212 Pivot Table Auto-Filter")
3. Click **Save**

### Step 6: Set Up the Automatic Trigger
1. In the Apps Script editor, find the dropdown menu that says "Select a function"
2. Choose **setTrigger** from the dropdown
3. Click the **Run** button (play icon)
4. When prompted, authorize the script to access your Google Sheet
   - Click "Review Permissions"
   - Click your email/account
   - Click "Allow" to grant permissions
5. You'll see a confirmation: "Trigger set: updatePivotTableToLatestDate will run every 5 minutes"

### Step 7: Verify Installation
1. In the Apps Script dropdown, select **testScript**
2. Click **Run**
3. Click **View > Logs** to see the test results
4. You should see:
   - "RawData" sheet found
   - "Óránkénti jelentés" sheet found
   - Number of pivot tables detected

## Usage

### Automatic Updates (Recommended)
Once the trigger is set up, the script will:
- Check your RawData sheet every 5 minutes
- Find the latest date
- Update the pivot table filter automatically

### Manual Update
To manually update the pivot table immediately:

1. In Google Apps Script, select **updatePivotTableToLatestDate** from the dropdown
2. Click **Run**
3. Check your Google Sheet - the pivot table should update within seconds

### Update to Specific Date
If you want to filter to a specific date instead of the latest:

1. In Google Apps Script, open the Logs section
2. Run the function: `updatePivotTableToSpecificDate("2025-11-12")`
3. Replace the date with your desired date in YYYY-MM-DD format

## How It Works

1. **Finds Latest Date**: Scans all dates in column A of the RawData sheet
2. **Identifies Pivot Table**: Locates the pivot table(s) in the Óránkénti jelentés sheet
3. **Updates Date Filter**: Applies a filter to show only rows matching the latest date
4. **Repeats**: Runs every 5 minutes to keep data current

## Troubleshooting

### Issue: Script doesn't find the RawData sheet
**Solution**: 
- Verify your sheet is named exactly "RawData"
- Check that it has data with dates in column A

### Issue: Script doesn't find the pivot table
**Solution**:
- Verify the sheet is named exactly "Óránkénti jelentés"
- Ensure a pivot table exists in this sheet
- The pivot table must have a date-based filter

### Issue: Filter isn't updating
**Solution**:
- Run `testScript()` to verify all components are found
- Check the Logs (View > Logs) for error messages
- Ensure the date column in RawData contains valid dates
- Manually run `updatePivotTableToLatestDate()` to test

### Issue: Script runs but nothing changes
**Solution**:
- The latest date might already be selected
- Check if the pivot table has been manually configured correctly
- Verify the date format matches (YYYY-MM-DD)

## Managing Triggers

### View Active Triggers
1. In Google Apps Script, click **Triggers** (alarm icon on left sidebar)
2. You should see "updatePivotTableToLatestDate" running every 5 minutes

### Remove Automatic Trigger
1. In Google Apps Script, select **removeTrigger** from the dropdown
2. Click **Run**
3. You'll see: "Trigger removed"

### Change Trigger Frequency
To change from 5 minutes to a different interval:
1. In the `setTrigger()` function, change `.everyMinutes(5)` to:
   - `.everyHours(1)` for hourly
   - `.everyDays(1)` for daily
   - `.everyMinutes(10)` for 10 minutes, etc.
2. Remove the old trigger by running `removeTrigger()`
3. Run `setTrigger()` again with the new interval

## Advanced: Modify for Different Sheet Names

If your sheet names are different:

1. In the Google Apps Script editor, find these lines:
   ```javascript
   const rawDataSheet = ss.getSheetByName("RawData");
   const reportSheet = ss.getSheetByName("Óránkénti jelentés");
   ```

2. Replace the sheet names with your actual sheet names:
   ```javascript
   const rawDataSheet = ss.getSheetByName("Your Data Sheet Name");
   const reportSheet = ss.getSheetByName("Your Report Sheet Name");
   ```

3. Save and re-run `setTrigger()`

## Monitoring

Check if the script is running correctly:
1. In Google Apps Script, click **View > Logs**
2. Look for entries like:
   - "Latest date found: YYYY-MM-DD"
   - "Pivot table filters updated successfully"

## Support

If you encounter issues:
1. Check the Logs in Google Apps Script (View > Logs)
2. Run `testScript()` to diagnose problems
3. Verify sheet and column names match exactly
4. Try running `updatePivotTableToLatestDate()` manually

## Notes

- The script uses the system's date interpretation (may be timezone-aware)
- If multiple pivot tables exist in Óránkénti jelentés, all will be updated
- The script only modifies the date filter; other pivot table settings remain unchanged
- Execution logs are available for 30 days in Google Apps Script
