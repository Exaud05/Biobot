from opentrons import protocol_api

metadata = {
    "protocolName": "Default Serial Dilution - OT-2",
    "author": "OpenAI",
    "description": (
        "Performs a default 8-point 1:2 serial dilution across wells A1-A8 "
        "of a 96-well plate using an OT-2, P300 Single-Channel pipette, "
        "300 uL tips, and a 12-channel reservoir."
    ),
    "apiLevel": "2.15",
}


def run(protocol: protocol_api.ProtocolContext):
    # -----------------------------
    # Default protocol parameters
    # -----------------------------
    num_dilutions = 8
    diluent_volume_ul = 100
    stock_volume_ul = 100
    transfer_volume_ul = 100
    mix_volume_ul = 80
    mix_repetitions = 5

    # -----------------------------
    # Deck setup
    # -----------------------------
    reservoir = protocol.load_labware(
        "nest_12_reservoir_15ml",
        "1",
        label="Reagent Reservoir"
    )

    plate = protocol.load_labware(
        "corning_96_wellplate_360ul_flat",
        "2",
        label="Serial Dilution Plate"
    )

    tiprack = protocol.load_labware(
        "opentrons_96_tiprack_300ul",
        "3",
        label="300 uL Tip Rack"
    )

    pipette = protocol.load_instrument(
        "p300_single_gen2",
        mount="right",
        tip_racks=[tiprack]
    )

    # -----------------------------
    # Reagent locations
    # -----------------------------
    diluent = reservoir["A1"]
    stock = reservoir["A2"]
    waste = reservoir["A12"]

    dilution_wells = plate.rows()[0][:num_dilutions]

    # -----------------------------
    # User preparation instructions
    # -----------------------------
    protocol.comment("Deck setup:")
    protocol.comment("Slot 1: NEST 12-well reservoir")
    protocol.comment("Slot 2: Corning 96-well flat-bottom plate")
    protocol.comment("Slot 3: Opentrons 300 uL tip rack")
    protocol.comment("")
    protocol.comment("Reservoir setup before starting:")
    protocol.comment("A1: Diluent, at least 2 mL recommended")
    protocol.comment("A2: Stock sample, at least 500 uL recommended")
    protocol.comment("A12: Empty waste well")
    protocol.comment("")
    protocol.comment("Output dilution series will be in plate wells A1-A8.")
    protocol.comment("Final volume in each dilution well: 100 uL.")
    protocol.comment("Dilution factors: A1 = 1:2, A2 = 1:4, A3 = 1:8, etc.")

    # -----------------------------
    # Step 1: Add diluent to A1-A8
    # -----------------------------
    protocol.comment("Adding 100 uL diluent to wells A1-A8.")

    pipette.pick_up_tip()
    for well in dilution_wells:
        pipette.aspirate(diluent_volume_ul, diluent)
        pipette.dispense(diluent_volume_ul, well)
        pipette.touch_tip(well)
    pipette.drop_tip()

    # -----------------------------
    # Step 2: Add stock to first well
    # -----------------------------
    protocol.comment("Adding 100 uL stock sample to well A1.")

    first_well = dilution_wells[0]

    pipette.pick_up_tip()
    pipette.aspirate(stock_volume_ul, stock)
    pipette.dispense(stock_volume_ul, first_well)
    pipette.mix(mix_repetitions, mix_volume_ul, first_well)
    pipette.touch_tip(first_well)
    pipette.drop_tip()

    # -----------------------------
    # Step 3: Perform serial dilution
    # -----------------------------
    protocol.comment("Performing 1:2 serial dilution across A1-A8.")

    for index in range(num_dilutions - 1):
        source_well = dilution_wells[index]
        destination_well = dilution_wells[index + 1]

        protocol.comment(
            f"Transferring {transfer_volume_ul} uL from "
            f"{source_well.display_name} to {destination_well.display_name}."
        )

        pipette.pick_up_tip()
        pipette.mix(3, mix_volume_ul, source_well)
        pipette.aspirate(transfer_volume_ul, source_well)
        pipette.dispense(transfer_volume_ul, destination_well)
        pipette.mix(mix_repetitions, mix_volume_ul, destination_well)
        pipette.touch_tip(destination_well)
        pipette.drop_tip()

    # -----------------------------
    # Step 4: Remove excess from final well
    # -----------------------------
    protocol.comment("Removing 100 uL excess from final dilution well A8.")

    final_well = dilution_wells[-1]

    pipette.pick_up_tip()
    pipette.aspirate(transfer_volume_ul, final_well)
    pipette.dispense(transfer_volume_ul, waste)
    pipette.blow_out(waste)
    pipette.drop_tip()

    protocol.comment("Serial dilution complete.")