from opentrons import protocol_api

metadata = {
    'protocolName': 'Serial Dilution 1:12 (starting from column 3)',
    'author': 'Generated for OT-2',
    'description': '1:12 serial dilution starting from column 3 of a 96-well plate. '
                   'Columns 1 and 2 are left untouched (e.g. stock / pre-dilution). '
                   'Sample is loaded in column 3. Diluent is pre-loaded in columns 4-10.',
    'apiLevel': '2.13'
}

# ── Parameters ────────────────────────────────────────────────────────────────
TOTAL_VOLUME    = 240   # µL per well
TRANSFER_VOLUME = 20    # µL transferred each step  (20 / 240 = 1:12)
DILUENT_VOLUME  = TOTAL_VOLUME - TRANSFER_VOLUME  # 220 µL diluent pre-loaded
START_COLUMN    = 2     # 0-indexed → column 3 on the plate
NUM_DILUTIONS   = 8     # number of dilution steps (cols 3-10)
MIX_REPS        = 5     # mix repetitions after each transfer
MIX_VOLUME      = 150   # µL used for mixing


def run(protocol: protocol_api.ProtocolContext):

    # ── Labware ───────────────────────────────────────────────────────────────
    tips      = protocol.load_labware('opentrons_96_tiprack_300ul', 1)
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 2)
    plate     = protocol.load_labware('nest_96_wellplate_200ul_flat', 3)

    # ── Pipette ───────────────────────────────────────────────────────────────
    p300 = protocol.load_instrument('p300_multi_gen2', 'left', tip_racks=[tips])

    # ── Liquid references ─────────────────────────────────────────────────────
    diluent = reservoir['A1']   # fill reservoir column 1 with diluent (~12 mL)

    columns = plate.columns()   # 12 columns, 0-indexed

    # Columns involved in this protocol (0-indexed: 2 = col3, up to col10)
    dilution_columns = columns[START_COLUMN: START_COLUMN + NUM_DILUTIONS]

    # ── Step 1: Add diluent to destination columns (col 4-10) ─────────────────
    protocol.comment('--- Adding diluent to columns 4-10 (skipping cols 1-2) ---')
    p300.pick_up_tip()
    for col in dilution_columns[1:]:              # skip first (col 3 = sample source)
        p300.aspirate(DILUENT_VOLUME, diluent)
        p300.dispense(DILUENT_VOLUME, col[0])
        p300.blow_out(col[0].top())
    p300.drop_tip()

    # ── Step 2: Serial dilution col3 → col4 → … → col10 ─────────────────────
    protocol.comment('--- Performing 1:12 serial dilution from column 3 ---')
    for i in range(NUM_DILUTIONS - 1):
        source = dilution_columns[i][0]
        dest   = dilution_columns[i + 1][0]

        p300.pick_up_tip()
        # Mix source before aspirating
        p300.mix(MIX_REPS, MIX_VOLUME, source)
        # Transfer
        p300.aspirate(TRANSFER_VOLUME, source)
        p300.dispense(TRANSFER_VOLUME, dest)
        # Mix destination after dispensing
        p300.mix(MIX_REPS, MIX_VOLUME, dest)
        p300.blow_out(dest.top())
        p300.drop_tip()

    protocol.comment('--- Serial dilution complete ---')