from opentrons import protocol_api

metadata = {
    "protocolName": "OT-2 3-fold Serial Dilution (Columns) with P300 Multi",
    "author": "Opentrons Assistant",
    "description": "Performs a 3-fold (1:3) serial dilution across columns of a 96-well plate using a P300 multi-channel pipette. Change NUM_COLUMNS to 3 if you want only 3 concentrations.",
    "apiLevel": "2.14",
}

def run(protocol: protocol_api.ProtocolContext):
    # =========================
    # USER CONFIGURATION
    # =========================
    # Set number of columns to dilute across (max 12). Set to 3 if you want 3 concentrations (cols 1–3).
    NUM_COLUMNS = 12

    # Dilution factor (3-fold = each step is 1/3 of previous concentration)
    DILUTION_FACTOR = 3.0

    # Volume transferred between columns each step (uL)
    TRANSFER_VOL = 100.0

    # Reservoir wells
    DILUENT_WELL_NAME = "A12"  # place diluent here
    STOCK_WELL_NAME = "A1"     # place stock here

    # Labware and instruments (edit slots/names as needed)
    plate_slot = 1
    tiprack_slots = [2, 3]
    reservoir_slot = 4
    pipette_mount = "left"

    plate_load_name = "corning_96_wellplate_360ul_flat"
    reservoir_load_name = "usascientific_12_reservoir_22ml"
    tiprack_load_name = "opentrons_96_tiprack_300ul"
    pipette_name = "p300_multi"

    # =========================
    # DERIVED VOLUMES (do not edit unless you know what you're doing)
    # =========================
    # To achieve a 3-fold step, prefill each destination with (factor-1)*transfer volume.
    DILUENT_PREVOLUME = TRANSFER_VOL * (DILUTION_FACTOR - 1.0)  # e.g., 200 uL
    FINAL_VOL = DILUENT_PREVOLUME + TRANSFER_VOL                # e.g., 300 uL in each diluted column
    MIX_VOL = min(200.0, FINAL_VOL - 50.0)                      # safe mixing volume with headroom

    if NUM_COLUMNS < 2 or NUM_COLUMNS > 12:
        raise ValueError("NUM_COLUMNS must be between 2 and 12.")

    if FINAL_VOL > 360:
        raise ValueError("Final volume per well exceeds 96-flat well capacity. Reduce TRANSFER_VOL or factor.")

    # =========================
    # LOAD LABWARE
    # =========================
    plate = protocol.load_labware(plate_load_name, plate_slot)
    tipracks = [protocol.load_labware(tiprack_load_name, s) for s in tiprack_slots]
    reservoir = protocol.load_labware(reservoir_load_name, reservoir_slot)

    p300 = protocol.load_instrument(pipette_name, pipette_mount, tip_racks=tipracks)

    diluent = reservoir.wells_by_name()[DILUENT_WELL_NAME]
    stock = reservoir.wells_by_name()[STOCK_WELL_NAME]

    # Optional: adjust well-bottom clearances (useful for shallow plates/reservoirs)
    p300.well_bottom_clearance.aspirate = 1.0
    p300.well_bottom_clearance.dispense = 1.0

    # =========================
    # STEPS
    # =========================

    # 1) Pre-fill diluent into columns 2..NUM_COLUMNS (e.g., 200 uL for 3-fold)
    #    Column 1 will contain undiluted stock, so do not add diluent there.
    for dest_col in plate.columns()[1:NUM_COLUMNS]:
        p300.pick_up_tip()
        p300.transfer(
            DILUENT_PREVOLUME,
            diluent,
            dest_col,
            new_tip="never",
            blow_out=True,
            blowout_location="destination well"
        )
        p300.drop_tip()

    # 2) Seed column 1 with stock so there's enough volume to start the series.
    #    We load FINAL_VOL of stock into column 1 (e.g., 300 uL).
    #    Note: After the series, col 1 will have less volume (FINAL_VOL - TRANSFER_VOL).
    p300.transfer(
        FINAL_VOL,
        stock,
        plate.columns()[0],
        new_tip="always"
    )

    # 3) Perform 3-fold serial dilution across columns
    #    Transfer TRANSFER_VOL from each column to the next, with mixing after at the destination.
    columns = plate.columns()
    for i in range(NUM_COLUMNS - 1):
        src = columns[i]
        dst = columns[i + 1]
        p300.transfer(
            TRANSFER_VOL,
            src,
            dst,
            mix_after=(3, MIX_VOL),
            new_tip="always"
        )

    # 4) Remove TRANSFER_VOL from the last column to keep its final volume equal to other diluted columns.
    p300.transfer(
        TRANSFER_VOL,
        columns[NUM_COLUMNS - 1],
        protocol.fixed_trash["A1"],
        new_tip="always",
        blow_out=True
    )

    # Optional: Brief pause for user
    protocol.comment(f"3-fold serial dilution complete across columns 1 to {NUM_COLUMNS}.")
    protocol.comment("Tip: Set NUM_COLUMNS = 3 at the top if you only want 3 concentrations (columns 1–3).")
    protocol.comment("Diluent was in reservoir well "
                     f"{DILUENT_WELL_NAME}, stock was in {STOCK_WELL_NAME}.")