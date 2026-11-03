# Verified working protocol
# Platform: opentrons_ot2
# Approved by: Youssef EL KHALIDY
# Date: 2026-07-20T14:03:35.479928
# Chat: 384f355f-757a-4642-a647-4f57c1723633
# ---
from opentrons import protocol_api

metadata = {
    "protocolName": "1:12 Serial Dilution with Transfer and Mixing",
    "author": "OpenAI",
    "description": (
        "Performs a 1:12 serial dilution on an Opentrons OT-2 using standard labware "
        "and default-style parameters, including aspiration, dispense, and mixing steps."
    ),
    "apiLevel": "2.15",
}


def run(protocol: protocol_api.ProtocolContext):
    # Labware
    tiprack_300 = protocol.load_labware("opentrons_96_tiprack_300ul", "1")
    source_plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "2")
    dilution_plate = protocol.load_labware("corning_96_wellplate_360ul_flat", "3")
    reservoir = protocol.load_labware("nest_12_reservoir_15ml", "4")

    # Instrument
    p300 = protocol.load_instrument(
        "p300_single_gen2",
        mount="right",
        tip_racks=[tiprack_300],
    )

    # Parameters
    diluent_volume = 220  # uL added to wells A2-A12
    transfer_volume = 20  # uL transferred between wells
    mix_reps = 3
    mix_volume = 100  # uL
    source_sample_volume = 240  # uL transferred from source to first dilution well

    # Wells
    diluent = reservoir["A1"]
    source = source_plate["A1"]
    dilution_wells = dilution_plate.rows()[0][:12]  # A1-A12

    # Step 1: Add diluent to wells A2-A12
    p300.pick_up_tip()
    for well in dilution_wells[1:]:
        p300.aspirate(diluent_volume, diluent)
        p300.dispense(diluent_volume, well)
    p300.drop_tip()

    # Step 2: Add sample to first well and mix
    p300.pick_up_tip()
    p300.aspirate(source_sample_volume, source)
    p300.dispense(source_sample_volume, dilution_wells[0])
    p300.mix(mix_reps, mix_volume, dilution_wells[0])

    # Step 3: Perform serial dilution across row A
    # Each transfer moves 20 uL from one well into 220 uL diluent in the next well
    for i in range(11):
        source_well = dilution_wells[i]
        dest_well = dilution_wells[i + 1]

        p300.aspirate(transfer_volume, source_well)
        p300.dispense(transfer_volume, dest_well)
        p300.mix(mix_reps, mix_volume, dest_well)

    # Step 4: Remove excess from final well to equalize volumes
    p300.aspirate(transfer_volume, dilution_wells[11])
    p300.dispense(transfer_volume, protocol.fixed_trash["A1"])
    p300.drop_tip()