from typing import Optional


def mix_in_place(lh, well, volume_ul: int, cycles: int):
    """Simple in-place mix by repeated aspirate/dispense to avoid backend-specific mix APIs."""
    for _ in range(cycles):
        lh.aspirate(well, volume_ul)
        lh.dispense(well, volume_ul)


def serial_dilution_1to2_96_colwise(
    lh,
    plate,
    diluent_well,
    tip_rack,
    waste_well: Optional[object] = None,
    rows: str = "ABCDEFGH",
    n_cols: int = 12,
    prefill_vol_ul: int = 100,
    transfer_vol_ul: int = 100,
    mix_vol_ul: int = 150,
    mix_cycles: int = 3,
    premix_start_cycles: int = 2,
):
    """
    Perform a 1:2 serial dilution on a 96-well plate, column-wise (1→12), for all rows.

    Parameters
    - lh:            PyLabRobot LiquidHandler (e.g., using Hamilton STAR backend).
    - plate:         96-well plate resource, indexable by well name like plate["A1"].
    - diluent_well:  Well resource with diluent (e.g., reservoir["A1"]).
    - tip_rack:      Tip rack resource, indexable like tip_rack["A1"].
    - waste_well:    Optional waste well for final removal from last column.
    - rows:          Row letters to process (default "A".."H").
    - n_cols:        Number of plate columns (default 12).
    - prefill_vol_ul: Volume of diluent to prefill columns 2..n_cols (µL).
    - transfer_vol_ul: Volume to transfer each step from col c to c+1 (µL).
    - mix_vol_ul:    Volume used for mixing in destination after each transfer (µL).
    - mix_cycles:    Number of mix cycles after each transfer.
    - premix_start_cycles: Number of mix cycles in the starting well before first transfer.
    """

    if n_cols < 2:
        raise ValueError("n_cols must be at least 2 for a serial dilution.")

    # Pre-fill columns 2..n_cols with diluent
    for col in range(2, n_cols + 1):
        for row in rows:
            dest = plate[f"{row}{col}"]
            lh.aspirate(diluent_well, prefill_vol_ul)
            lh.dispense(dest, prefill_vol_ul)

    # Perform serial dilution per row
    for row in rows:
        # Use one tip per row
        tip_pos = tip_rack[f"{row}1"]
        lh.pick_up_tips(tip_pos)

        # Optional pre-mix in starting well to homogenize sample in col 1
        start = plate[f"{row}1"]
        if premix_start_cycles > 0 and mix_vol_ul > 0:
            mix_in_place(lh, start, mix_vol_ul, premix_start_cycles)

        # Transfer along the row: col 1→2, 2→3, ..., (n_cols-1)→n_cols
        for col in range(1, n_cols):
            src = plate[f"{row}{col}"]
            dst = plate[f"{row}{col + 1}"]

            lh.aspirate(src, transfer_vol_ul)
            lh.dispense(dst, transfer_vol_ul)

            if mix_cycles > 0 and mix_vol_ul > 0:
                mix_in_place(lh, dst, mix_vol_ul, mix_cycles)

        # After the final step, optionally remove from last column to keep volumes equal
        if waste_well is not None and transfer_vol_ul > 0:
            last = plate[f"{row}{n_cols}"]
            lh.aspirate(last, transfer_vol_ul)
            lh.dispense(waste_well, transfer_vol_ul)

        lh.drop_tips()

    # Optional: add pauses/logs around steps outside this function as needed.


# Example integration (fill in your actual resources and backend):
#
# from pylabrobot.liquid_handling import LiquidHandler
# from pylabrobot.liquid_handling.backends.hamilton import STAR
# from pylabrobot.resources import Resource  # use your specific resource classes
#
# async def main():
#     lh = LiquidHandler(backend=STAR(ip="127.0.0.1", port=12345))
#     await lh.setup()
#
#     # TODO: add your real deck and resources here:
#     # deck = <your Hamilton deck/carriers>
#     # plate = <your 96-well plate resource on the deck>
#     # tip_rack = <your 300 µL tip rack>
#     # reservoir = <your reagent reservoir>
#     # waste = <your waste reservoir>
#
#     # serial_dilution_1to2_96_colwise(
#     #     lh=lh,
#     #     plate=plate,
#     #     diluent_well=reservoir["A1"],
#     #     tip_rack=tip_rack,
#     #     waste_well=waste["A1"],  # or None to skip final removal
#     #     rows="ABCDEFGH",
#     #     n_cols=12,
#     #     prefill_vol_ul=100,
#     #     transfer_vol_ul=100,
#     #     mix_vol_ul=150,
#     #     mix_cycles=3,
#     #     premix_start_cycles=2,
#     # )
#
#     # await lh.teardown()
#
# # if __name__ == "__main__":
# #     import asyncio
# #     asyncio.run(main())