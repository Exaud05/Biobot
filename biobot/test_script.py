from opentrons import protocol_api

metadata = {
    'apiLevel': '2.13',
    'protocolName': '1:10 Serial Dilution (Multi-channel)'
}

def run(protocol: protocol_api.ProtocolContext):
    # 1. Define Labware
    tiprack = protocol.load_labware('opentrons_96_tiprack_300ul', 1)
    plate = protocol.load_labware('nest_96_wellplate_200ul_flat', 2)
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 3)

    # 2. Define Pipette
    pipette = protocol.load_instrument('p300_multi_gen2', 'right', tip_racks=[tiprack])

    # 3. Define Reagents
    diluent = reservoir.wells_by_name()['A1']
    # Samples are already loaded in column 1 of the plate by the user
    
    # 4. Volumes
    diluent_vol = 180
    transfer_vol = 20
    mix_vol = 100  # Mix volume (must be less than well capacity)

    # 5. Add Diluent to Columns 2 through 12
    # Using a multi-channel pipette, we operate by columns
    pipette.pick_up_tip()
    for col in range(1, 12): # Columns 2 to 12 (Index 1 to 11)
        dest_col = plate.columns()[col]
        pipette.aspirate(diluent_vol, diluent)
        pipette.dispense(diluent_vol, dest_col)
    pipette.drop_tip()

    # 6. Perform Serial Dilution (Col 1 -> Col 2 -> ... -> Col 12)
    pipette.pick_up_tip()
    
    for col in range(0, 11): # Index 0 to 10 (Columns 1 to 11)
        source_col = plate.columns()[col]
        dest_col = plate.columns()[col + 1]
        
        # Mix the source well thoroughly before transferring
        pipette.mix(5, mix_vol, source_col)
        
        # Aspirate transfer volume from source
        pipette.aspirate(transfer_vol, source_col)
        
        # Dispense into destination
        pipette.dispense(transfer_vol, dest_col)
        
        # Mix the destination well
        pipette.mix(5, mix_vol, dest_col)
        
    # Drop the final tip
    pipette.drop_tip()