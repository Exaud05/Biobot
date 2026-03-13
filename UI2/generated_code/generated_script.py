from opentrons import protocol_api

metadata = {
    "protocolName": "OT-2 Serial Dilution (Single-Channel)",
    "author": "Opentrons Lab Automation Assistant",
    "description": "Dispense diluent to a 96-well plate, then perform 8 parallel serial dilutions across columns.",
    "apiLevel": "2.14",
}

def run(protocol: protocol_api.ProtocolContext):
    # Labware
    plate = protocol.load_labware("corning_96_wellplate_360ul_flat", 1)
    tiprack_1 = protocol.load_labware("opentrons_96_tiprack_300ul", 2)
    tiprack_2 = protocol.load_labware("opentrons_96_tiprack_300ul", 3)
    reservoir = protocol.load_labware("usascientific_12_reservoir_22ml", 4)

    # Pipette
    p300 = protocol.load_instrument(
        "p300_single_gen2",
        "left",
        tip_racks=[tiprack_1, tiprack_2],
    )

    # Liquids in reservoir:
    # - A1–A8: 8 different samples
    # - A12: diluent
    diluent = reservoir.wells_by_name()["A12"]
    samples = reservoir.wells()[:8]  # A1–A8

    # Step 1: dispense diluent (50 µL) into every well of the plate
    p300.distribute(50, diluent, plate.wells())

    # Step 2: for each row (A–H), add sample to first column and serially dilute across the row
    for row_idx, row in enumerate(plate.rows()):
        source = samples[row_idx]

        p300.pick_up_tip()

        # Seed first well in the row with 30 µL sample, then mix
        p300.transfer(30, source, row[0], mix_after=(3, 25), new_tip="never")

        # Serially transfer 30 µL from each well to the next across the row, mixing after each transfer
        p300.transfer(30, row[:11], row[1:], mix_after=(3, 25), new_tip="never")

        # Optional: remove 30 µL from the last well to keep volumes uniform (uncomment to enable)
        # p300.transfer(30, row[-1], protocol.fixed_trash["A1"], new_tip="never")

        p300.drop_tip()
