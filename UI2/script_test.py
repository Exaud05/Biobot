# Opentrons OT-2 API v2 example: moving liquids between wells

metadata = {
    "protocolName": "Basic Well-to-Well Liquid Moves (Examples)",
    "author": "Assistant",
    "description": "Demonstrates single, many-to-many, one-to-many (distribute), and many-to-one (consolidate) moves",
    "apiLevel": "2.14",
}

from opentrons import protocol_api


def run(ctx: protocol_api.ProtocolContext):
    # Labware
    plate = ctx.load_labware("corning_96_wellplate_360ul_flat", "1", "96-well plate")
    reservoir = ctx.load_labware("nest_12_reservoir_15ml", "2", "12-channel reservoir")
    tiprack300 = ctx.load_labware("opentrons_96_tiprack_300ul", "3")

    # Pipette
    p300 = ctx.load_instrument("p300_single_gen2", "right", tip_racks=[tiprack300])

    # Optional: adjust speeds (uL/s)
    # p300.flow_rate.aspirate = 100
    # p300.flow_rate.dispense = 150
    # p300.flow_rate.blow_out = 200

    # 1) Single well-to-well transfer
    # Move 100 µL from A1 to A2 on the same plate
    p300.transfer(
        100,
        plate.wells_by_name()["A1"],
        plate.wells_by_name()["A2"],
        new_tip="always",
        mix_before=(2, 80),   # optional: mix source before aspirating
        mix_after=(2, 80),    # optional: mix destination after dispensing
    )

    # 2) Many-to-many: column 1 to column 2 (A1..H1 -> A2..H2)
    src_col1 = plate.columns_by_name()["1"]  # [A1, B1, ..., H1]
    dst_col2 = plate.columns_by_name()["2"]  # [A2, B2, ..., H2]
    p300.transfer(
        100,
        src_col1,
        dst_col2,
        new_tip="always",  # set to "once" to reuse one tip across the whole series
    )

    # 3) One-to-many: distribute from reservoir A1 to all wells in column 3
    # Distribute uses minimal aspirations with a disposal volume to improve accuracy.
    dest_col3 = plate.columns_by_name()["3"]  # list of 8 destination wells
    p300.distribute(
        50,
        reservoir.wells_by_name()["A1"],
        dest_col3,
        new_tip="once",
        disposal_volume=10,  # extra held in tip to reduce carryover error
    )

    # 4) Many-to-one: consolidate multiple wells into a single destination
    # Example: pool A1..A6 into A12 (50 µL each, total 300 µL)
    sources_to_pool = plate.rows_by_name()["A"][:6]  # [A1, A2, A3, A4, A5, A6]
    pool_dest = plate.wells_by_name()["A12"]
    p300.consolidate(
        50,
        sources_to_pool,
        pool_dest,
        new_tip="always",
    )

    # 5) Custom mapping via iteration: row B to row C (first 6 wells)
    for s, d in zip(plate.rows_by_name()["B"][:6], plate.rows_by_name()["C"][:6]):
        p300.transfer(
            75,
            s,
            d,
            new_tip="always",
        )

    # Tip handling notes:
    # - Use new_tip="always" for safest operation (fresh tip per transfer).
    # - Use new_tip="once" to reuse a single tip across a series (risk of carryover).
    # - For distribute, prefer new_tip="once" with a disposal_volume.