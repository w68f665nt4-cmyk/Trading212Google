/**
 * Pivot Table Auto-Filter for Trading212 Google Sheet
 * 
 * This Google Apps Script automatically updates the date filter in the
 * "Óránkénti jelentés" (Hourly Report) pivot table to show only the
 * latest date from the RawData sheet.
 * 
 * INSTALLATION:
 * 1. Open your Google Sheet
 * 2. Go to Extensions > Apps Script
 * 3. Delete any existing code
 * 4. Paste this entire script
 * 5. Save the project
 * 6. Run the setTrigger() function from the dropdown menu
 * 7. Authorize when prompted
 * 
 * The script will run automatically when new data is added to trigger
 * the pivot table filter update.
 */

/**
 * Main function to update pivot table date filter to latest date
 */
function updatePivotTableToLatestDate() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const rawDataSheet = ss.getSheetByName("RawData");
  const reportSheet = ss.getSheetByName("Óránkénti jelentés");
  
  if (!rawDataSheet || !reportSheet) {
    Logger.log("Error: Could not find RawData or Óránkénti jelentés sheet");
    return;
  }
  
  // Get all data from RawData sheet
  const data = rawDataSheet.getDataRange().getValues();
  
  if (data.length < 2) {
    Logger.log("No data in RawData sheet");
    return;
  }
  
  // Find the latest date in column A (Date column)
  const dates = [];
  for (let i = 1; i < data.length; i++) {
    const dateValue = data[i][0];
    if (dateValue) {
      dates.push(new Date(dateValue));
    }
  }
  
  if (dates.length === 0) {
    Logger.log("No dates found in RawData");
    return;
  }
  
  // Get the latest date
  const latestDate = new Date(Math.max.apply(null, dates));
  const latestDateString = formatDate(latestDate);
  
  Logger.log("Latest date found: " + latestDateString);
  
  // Get all pivot tables in the report sheet
  const pivots = reportSheet.getPivotTables();
  
  if (pivots.length === 0) {
    Logger.log("No pivot tables found in Óránkénti jelentés sheet");
    return;
  }
  
  // Update each pivot table's date filter
  for (let i = 0; i < pivots.length; i++) {
    const pivot = pivots[i];
    updatePivotFilters(pivot, latestDateString);
  }
  
  Logger.log("Pivot table filters updated successfully");
}

/**
 * Update pivot table filters to show only the latest date
 * @param {PivotTable} pivot - The pivot table to update
 * @param {string} latestDateString - The latest date as a string
 */
function updatePivotFilters(pivot, latestDateString) {
  const filters = pivot.getFilters();
  
  for (let i = 0; i < filters.length; i++) {
    const filter = filters[i];
    const sourceColumn = filter.getSourceDataColumn();
    
    // Check if this filter is on the Date column (column 0 in RawData)
    if (sourceColumn === 0 || filter.getSourceDataColumnName().toLowerCase().includes("date")) {
      try {
        // Remove all current filter criteria
        filter.resetCriteria();
        
        // Set the filter to show only the latest date
        const criteria = SpreadsheetApp.newFilterCriteria()
          .whenCellExactly(latestDateString)
          .build();
        
        filter.setCriteria(criteria);
        Logger.log("Updated date filter to: " + latestDateString);
      } catch (e) {
        Logger.log("Error updating date filter: " + e.toString());
        
        // Alternative approach: try by column header name
        const sourceColumnName = filter.getSourceDataColumnName();
        if (sourceColumnName && sourceColumnName.toLowerCase() === "date") {
          try {
            filter.resetCriteria();
            const criteria = SpreadsheetApp.newFilterCriteria()
              .whenCellExactly(latestDateString)
              .build();
            filter.setCriteria(criteria);
            Logger.log("Updated date filter (by name) to: " + latestDateString);
          } catch (e2) {
            Logger.log("Alternative filter update also failed: " + e2.toString());
          }
        }
      }
    }
  }
}

/**
 * Format date to YYYY-MM-DD format
 * @param {Date} date - The date to format
 * @return {string} Formatted date string
 */
function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return year + '-' + month + '-' + day;
}

/**
 * Set up a time-based trigger to run the update function
 * This will check and update the pivot table every 5 minutes
 * 
 * IMPORTANT: Run this function once from the Apps Script editor
 * to set up the automatic trigger
 */
function setTrigger() {
  // Remove existing triggers to avoid duplicates
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'updatePivotTableToLatestDate') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  
  // Create a new trigger that runs every 5 minutes
  ScriptApp.newTrigger('updatePivotTableToLatestDate')
    .timeBased()
    .everyMinutes(5)
    .create();
  
  Logger.log("Trigger set: updatePivotTableToLatestDate will run every 5 minutes");
}

/**
 * Remove the automatic trigger if needed
 */
function removeTrigger() {
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'updatePivotTableToLatestDate') {
      ScriptApp.deleteTrigger(triggers[i]);
      Logger.log("Trigger removed");
      return;
    }
  }
  Logger.log("No trigger found to remove");
}

/**
 * Alternative function: Update pivot table using a specific date
 * Use this if you want to manually set a specific date
 * 
 * @param {string} dateString - Date in YYYY-MM-DD format
 */
function updatePivotTableToSpecificDate(dateString) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const reportSheet = ss.getSheetByName("Óránkénti jelentés");
  
  if (!reportSheet) {
    Logger.log("Error: Could not find Óránkénti jelentés sheet");
    return;
  }
  
  const pivots = reportSheet.getPivotTables();
  
  if (pivots.length === 0) {
    Logger.log("No pivot tables found");
    return;
  }
  
  for (let i = 0; i < pivots.length; i++) {
    const pivot = pivots[i];
    updatePivotFilters(pivot, dateString);
  }
  
  Logger.log("Pivot tables updated to show: " + dateString);
}

/**
 * Test function to verify the script is working
 */
function testScript() {
  Logger.log("=== Testing Pivot Table Auto-Filter ===");
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const rawDataSheet = ss.getSheetByName("RawData");
  
  if (!rawDataSheet) {
    Logger.log("Error: RawData sheet not found");
    return;
  }
  
  const data = rawDataSheet.getDataRange().getValues();
  Logger.log("Total rows in RawData: " + data.length);
  Logger.log("First row (headers): " + data[0].join(", "));
  
  if (data.length > 1) {
    Logger.log("Last row date: " + data[data.length - 1][0]);
  }
  
  const reportSheet = ss.getSheetByName("Óránkénti jelentés");
  if (!reportSheet) {
    Logger.log("Error: Óránkénti jelentés sheet not found");
  } else {
    Logger.log("Óránkénti jelentés sheet found");
    const pivots = reportSheet.getPivotTables();
    Logger.log("Number of pivot tables: " + pivots.length);
  }
  
  Logger.log("=== Test Complete ===");
}
