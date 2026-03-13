import asyncio
from typing import Optional
import pylabrobot

# -------------------------------
# PyLabRobot imports
# -------------------------------
from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends import LiquidHandlerChatterboxBackend
from pylabrobot.resources.hamilton import STARDeck

from pylabrobot.resources import (
    TIP_CAR_480_A00,
    PLT_CAR_L5AC_A00,
    DeepWell_96_Well,
    geb_96_tiprack_1000ul,
    Trough
)

# -------------------------------
# Mixing helper
# -------------------------------
async def mix_in_place(lh, well, volume_ul: int, cycles: int):
    for _ in range(cycles):
        await lh.aspirate(well, volume_ul)
        await lh.dispense(well, volume_ul)


# -------------------------------
# Serial dilution protocol
# -------------------------------
async def serial_dilution_1to2_96_colwise(
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

    if n_cols < 2:
        raise ValueError("n_cols must be at least 2")

    # Prefill columns
    for col in range(2, n_cols + 1):
        for row in rows:
            dest = plate[f"{row}{col}"]
            await lh.aspirate(diluent_well, prefill_vol_ul)
            await lh.dispense(dest, prefill_vol_ul)

    # Serial dilution
    for row in rows:

        tip_pos = tip_rack[f"{row}1"]
        await lh.pick_up_tips(tip_pos)

        start = plate[f"{row}1"]

        if premix_start_cycles > 0:
            await mix_in_place(lh, start, mix_vol_ul, premix_start_cycles)

        for col in range(1, n_cols):
            src = plate[f"{row}{col}"]
            dst = plate[f"{row}{col+1}"]

            await lh.aspirate(src, transfer_vol_ul)
            await lh.dispense(dst, transfer_vol_ul)

            if mix_cycles > 0:
                await mix_in_place(lh, dst, mix_vol_ul, mix_cycles)

        if waste_well is not None:
            last = plate[f"{row}{n_cols}"]
            await lh.aspirate(last, transfer_vol_ul)
            await lh.dispense(waste_well, transfer_vol_ul)

        await lh.drop_tips()


# -------------------------------
# MAIN
# -------------------------------
async def main():

    # Backend
    backend = LiquidHandlerChatterboxBackend()
    lh = LiquidHandler(backend=backend, deck=STARDeck())

    # -------- Tip carrier --------
    tip_car = TIP_CAR_480_A00(name="tip carrier")
    tiprack = geb_96_tiprack_1000ul(name="tips_01")
    tip_car[0] = tiprack

    lh.deck.assign_child_resource(tip_car, rails=3)

    # -------- Plate carrier --------
    plt_car = PLT_CAR_L5AC_A00(name="plate carrier")
    plate = DeepWell_96_Well(name="plate_01")
    plt_car[0] = plate

    lh.deck.assign_child_resource(plt_car, rails=15)

    # -------- Reservoirs --------
    reservoir = Trough(name="reservoir")
    waste = Trough(name="waste")

    lh.deck.assign_child_resource(reservoir, rails=20)
    lh.deck.assign_child_resource(waste, rails=23)

    # Show layout
    lh.summary()

    await lh.setup()

    # -------- Run protocol --------
    await serial_dilution_1to2_96_colwise(
        lh=lh,
        plate=plate,
        diluent_well=reservoir["A1"],
        tip_rack=tiprack,
        waste_well=waste["A1"],
    )

    await lh.teardown()


# -------------------------------
if __name__ == "__main__":
    asyncio.run(main())
