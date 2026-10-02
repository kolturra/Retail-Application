# Manual test checklist

Run on a clean Windows 10 PC with the real installer, a real barcode scanner, and the printers you support.
Tick every line; write the build version and date at the bottom. Anything that fails blocks the release.

Note: the installer build (PyInstaller and Inno Setup) has not been run yet, so the build, its hidden imports and the
installed app are all untested until this checklist is worked through.

## 1. Install
- [ ] The installer runs on a PC with no Python installed.
- [ ] The app starts from the Start-menu shortcut (and the desktop shortcut if chosen).
- [ ] Launch the BUILT `RetailApp.exe` by hand once on a clean Windows PC: the build and `--selftest` never create a QApplication, so a missing Qt platform plugin or DLL would only show here.
- [ ] If the built app fails on a missing module, add it to the PyInstaller `hiddenimports` and rebuild (the spec has never been run).
- [ ] The window opens with no console box and no error dialog.
- [ ] `%LOCALAPPDATA%\RetailApp\` is created on first run (database, `app.log`, `backups\`).
- [ ] Windows SmartScreen shows the unsigned-app warning only (nothing is blocked outright).
- [ ] The installer was built with Inno Setup 6.3 or newer (needed for `x64compatible` and `{autopf}`).

## 2. Activation
- [ ] First run shows the activation window with a Machine ID.
- [ ] Copy copies the Machine ID; the WhatsApp request opens WhatsApp with the ID filled in.
- [ ] A key issued for a different PC is refused with a clear message and the window stays open.
- [ ] A valid key activates; restarting the app does not ask again.
- [ ] Quit at the activation window exits cleanly and creates no shop data.
- [ ] Run `python -m retail_ui` and the installed exe once each on a real PC: the activation modal flow works with a REAL vendor-issued licence key.
- [ ] The vendor generates licence keys with their private key, which lives outside the OneDrive-synced folder and is backed up.

## 3. Onboarding
- [ ] The first page lets you pick English, Hindi or Telugu and the next pages appear in that language.
- [ ] A GSTIN that does not match the chosen state is refused; a blank GSTIN is accepted.
- [ ] Choosing Grocery enables weighed items and credit; choosing Electronics enables serial, warranty and EMI.
- [ ] The backup page accepts a second folder (USB drive or synced folder) and creates it.
- [ ] Cancelling the wizard exits without creating a shop; finishing opens the Counter.
- [ ] Recovery mode: with an expired licence and no shop, only the Backup & Licence screen opens, with a notice.
- [ ] In recovery mode, restoring a backup shows the restart notice and the app works after restarting.
- [ ] Recover on a new PC from the second-location copy: install, activate, then Backup & Licence > Restore from file and pick the copy from the USB/synced folder; the shop data is back.

## 4. Grocery (kirana / general store)
- [ ] Scanning a barcode adds one line and the input is ready for the next scan with no mouse click.
- [ ] `3*` before a scan adds three; Enter on an empty input does nothing.
- [ ] A weighed item (rice) asks for the weight; `0.5*rice` adds half a kilo without asking.
- [ ] An unknown barcode opens New item with the barcode filled in; saving adds the line.
- [ ] Two items with similar names show a chooser.
- [ ] F2 customer, F3 hold, F4 held bills, F5 discount, F8 discard, Del delete line, F12 pay all work.
- [ ] A held bill survives closing and reopening the app; resuming it restores its lines.
- [ ] Pay by cash with "cash given" shows the change; split cash + UPI; credit (udhaar) needs a customer.
- [ ] The customer's udhaar balance rises after a credit sale and falls after Receive payment.
- [ ] Low-stock items are highlighted and listed under Stock.
- [ ] A 58 mm and an 80 mm thermal bill print on the real printer with nothing cut off.
- [ ] Return one item from Bills; stock goes back and the refund matches the bill.
- [ ] The Sales register and GST summary add up to the day's bills; CSV opens correctly in Excel.
- [ ] A 5,000-SKU catalogue stays responsive by hand when scanning, searching and listing.

## 5. Electronics (mobile / appliances)
- [ ] Selling a phone asks for the IMEI; a wrong or already-sold IMEI is refused with a clear message.
- [ ] Scanning the same IMEI twice on one bill is refused.
- [ ] Serial/IMEI sale: the sold unit shows as sold and cannot be sold again.
- [ ] Warranty months are shown on the bill.
- [ ] Batch tracking, where an item uses it, picks and shows the right batch.
- [ ] F7 (Change batch) on a batch-tracked line lists the item's batches with expiry and quantity, the current one preselected; choosing another updates the line, and an expired batch is marked EXPIRED.
- [ ] Paying with EMI is offered; the printed A4 invoice lists the IMEI and the warranty end date.
- [ ] A Purchase with several IMEIs (one per line) creates one unit each; a repeated IMEI is refused.
- [ ] Returning a phone puts that IMEI back in stock; serial items can only be returned whole.
- [ ] An inter-state customer's bill shows IGST; an in-state customer's shows CGST + SGST.
- [ ] Selling below stock behaves as the shop's policy says (block / warn / allow).

## 6. Languages
- [ ] Switching to Hindi and Telugu mid-bill keeps the lines and totals and retranslates every screen.
- [ ] Devanagari and Telugu text draws correctly (no empty boxes) on screens, in dialogs and on printed bills.
- [ ] The Nirmala UI font renders Devanagari and Telugu on a clean PC.
- [ ] No English text remains on any screen, dialog or error message in Hindi/Telugu (except brand/technical terms and state names, which are shown in English).
- [ ] The chosen language is remembered after restarting.
- [ ] A native speaker has reviewed the Hindi and Telugu strings (all hi/te strings are drafts).

## 7. Licence expiry
- [ ] With an expired key the red read-only banner shows and every write control is disabled.
- [ ] Viewing bills, reports, CSV export, printing, backup and restore still work.
- [ ] Counter shortcuts are disabled except F10/print; export, backup, restore and activation still work.
- [ ] Trying a blocked action by keyboard shortcut shows a translated message, never an English error.
- [ ] Entering a renewed key under Backup & License re-enables everything without restarting.

## 8. Backup and restore
- [ ] Closing the app creates one `daily-…` backup; closing again the same day does not create another.
- [ ] Back up now creates a file and lists it; the second folder gets a copy.
- [ ] With the second folder unavailable, the backup still succeeds and a clear warning is shown.
- [ ] Restore replaces the data after confirmation and every screen shows the restored data.
- [ ] Restoring a corrupt or unrelated file is refused and the current data is unchanged.
- [ ] After a restore, the app language and licence still work.

## 9. Hardware
- [ ] The barcode scanner works as a keyboard wedge into the counter with no driver and no focus problems.
- [ ] 58 mm thermal printer prints a full bill on a real roll printer.
- [ ] 80 mm thermal printer prints a full bill on a real roll printer.
- [ ] The thermal layout page height is 297 mm in code: verify the roll feed and cut on the hardware (no long blank tail, no cut mid-bill).
- [ ] An A4 printer prints a GST invoice.
- [ ] Save as PDF produces a readable file.
- [ ] The WhatsApp bill link opens WhatsApp or WhatsApp Web with the customer's number and bill details only.
- [ ] At the Counter, after paying, "WhatsApp last bill" is enabled (and nothing opens by itself); clicking it opens the same customer-and-bill-only message, and asks for a number when the customer has none.
- [ ] A 5,000-item catalogue stays responsive when scanning and searching.

## 10. Upgrade
- [ ] Installing a newer version over the old one keeps all data, the licence and the settings (`%LOCALAPPDATA%\RetailApp`).
- [ ] A new database migration runs once, after an automatic `pre-migrate` backup.
- [ ] Uninstalling the app leaves `%LOCALAPPDATA%\RetailApp\` in place.

## 11. Sign-off
- [ ] Build version: ________  Date: ________  Tested by: ________
- [ ] Every item above is ticked, or each failure has a ticket and is not a blocker.
