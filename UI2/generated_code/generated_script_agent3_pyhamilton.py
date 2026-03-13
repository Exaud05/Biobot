from typing import Optional


LAYOUT_PATH = "deck.lay"           # Path to your .lay (kept as a placeholder; simulation will load it if present)
PLATE_NAME = "plate_96"
TIPS_NAME = "tips_200ul"
RESERVOIR_NAME = "reservoir"
WASTE_NAME: Optional[str] = "waste"   # set to None to skip final removal from last column

ROWS = "ABCDEFGH"                  # rows to process on a 96-well plate
N_COLS = 12                        # number of columns on the plate

PREFILL_VOL_UL = 100               # µL of diluent into cols 2..12
TRANSFER_VOL_UL = 100              # µL transfer from col c to c+1
MIX_VOL_UL = 150                   # µL for mixing after each transfer
MIX_CYCLES = 3                     # number of mixes after each transfer
PREMIX_START_CYCLES = 2            # mixes in starting well before first transfer

# Import PyHamilton
from pyhamilton import (
    HamiltonInterface,
    LayoutManager,
    STAR,
    Plate96,
    Tip96,
)

def well_index_96(row_letter: str, col: int) -> int:
    """
    Convert row/col (e.g., A,1) to 1..96 index in column-major order:
      A1=1, B1=2, ..., H1=8, A2=9, ..., H12=96
    """
    row_letter = row_letter.upper()
    if row_letter not in "ABCDEFGH":
        raise ValueError(f"Invalid row: {row_letter}")
    if not (1 <= col <= 12):
        raise ValueError(f"Invalid col: {col}")
    row_idx = "ABCDEFGH".index(row_letter)  # 0..7
    return (col - 1) * 8 + row_idx + 1


def mix_in_place(star: STAR, resource, well_index: int, volume_ul: int, cycles: int, channel: int = 1):
    """Simple in-place mix by repeated aspirate/dispense."""
    if cycles <= 0 or volume_ul <= 0:
        return
    for _ in range(cycles):
        star.aspirate(resource, [well_index], [volume_ul], channels=[channel])
        star.dispense(resource, [well_index], [volume_ul], channels=[channel])


def serial_dilution_1to2_96_colwise_pyhamilton(
    layout_path: str = LAYOUT_PATH,
    plate_name: str = PLATE_NAME,
    tips_name: str = TIPS_NAME,
    reservoir_name: str = RESERVOIR_NAME,
    waste_name: Optional[str] = WASTE_NAME,
    rows: str = ROWS,
    n_cols: int = N_COLS,
    prefill_vol_ul: int = PREFILL_VOL_UL,
    transfer_vol_ul: int = TRANSFER_VOL_UL,
    mix_vol_ul: int = MIX_VOL_UL,
    mix_cycles: int = MIX_CYCLES,
    premix_start_cycles: int = PREMIX_START_CYCLES,
):
    """
    Run a 1:2 serial dilution on a 96-well plate using PyHamilton, in simulate mode.
    """
    if n_cols < 2:
        raise ValueError("n_cols must be at least 2 for a serial dilution.")

    # Connect to the instrument in simulate mode only.
    with HamiltonInterface as ham_int:
        # Load layout (if the file exists in your environment it will be used; otherwise
        # simulation will still proceed but may warn if resources cannot be resolved).
        lmgr = LayoutManager(layout_path)

        # Assign resources by type/name.
        plate = lmgr.assign_child_resource(Plate96, plate_name)
        tip_rack = lmgr.assign_child_resource(Tip96, tips_name)
        # For simulation purposes, we use Plate96 for reservoir/waste as generic multi-well resources.
        reservoir = lmgr.assign_child_resource(Plate96, reservoir_name)
        waste = lmgr.assign_child_resource(Plate96, waste_name) if waste_name is not None else None

        # Initialize STAR
        star = STAR(ham_int)
        star.initialize()

        channel = 1  # single-channel operations
        # Pre-fill columns 2..n_cols with diluent (one tip per row)
        for row in rows:
            star.pick_up_tips(tip_rack, tips=[channel])
            for col in range(2, n_cols + 1):
                dst_well = well_index_96(row, col)
                star.aspirate(reservoir, [1], [prefill_vol_ul], channels=[channel])  # reservoir A1 assumed as source
                star.dispense(plate, [dst_well], [prefill_vol_ul], channels=[channel])
            star.drop_tips(tip_rack, tips=[channel])

        # Perform serial dilution row by row
        for row in rows:
            start_idx = well_index_96(row, 1)
            star.pick_up_tips(tip_rack, tips=[channel])

            # Optional pre-mix in starting well
            mix_in_place(star, plate, start_idx, mix_vol_ul, premix_start_cycles, channel=channel)

            # Transfers along the row
            for col in range(1, n_cols):
                src = well_index_96(row, col)
                dst = well_index_96(row, col + 1)

                star.aspirate(plate, [src], [transfer_vol_ul], channels=[channel])
                star.dispense(plate, [dst], [transfer_vol_ul], channels=[channel])

                mix_in_place(star, plate, dst, mix_vol_ul, mix_cycles, channel=channel)

            # Optionally remove from last column to waste to equalize volumes
            if waste is not None and transfer_vol_ul > 0:
                last = well_index_96(row, n_cols)
                star.aspirate(plate, [last], [transfer_vol_ul], channels=[channel])
                star.dispense(waste, [1], [transfer_vol_ul], channels=[channel])  # waste A1 assumed

            star.drop_tips(tip_rack, tips=[channel])

        # End of simulated run
        star.stop()

if __name__ == "__main__":
    # Run with all defaults in simulate mode
    serial_dilution_1to2_96_colwise_pyhamilton()