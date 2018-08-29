import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer, Human
from sc2.constants import *
from sc2.ids.unit_typeid import *
from sc2.ids.ability_id import *
import asyncio
# pylint: disable=E0602

class ZergBot(sc2.BotAI):
    def __init__(self):
        self.OVERLORD_CHECK = 2
        self.DRONE_LIMIT = 70
        self.metabolic_boost = False
        self.overlord_speed = False
        self.roach_speed = False
        self.first_wave = False
        self.worker_production_allowed = True
        self.roach_production_allowed = True
        self.next_expansion_location = None
        self.DRONE_MORPH_LIMIT = 2
        self.OVERLORD_MORPH_LIMIT = 1
        self.queen_pairs = {}
        self.drone_morph_count = 0
        self.wave = 0

    async def on_step(self, iteration):
        if iteration == 0:
            await self.chat_send("glhf")
        
        self.worker_production_allowed = True
        self.roach_production_allowed = True

        await self.distribute_workers()
        await self.build_structures()
        await self.scout()
        await self.expand()
        await self.upgrade()
        await self.build_army()
        await self.attack()
        await self.defend()
        await self.check_overlord()
        await self.queen_inject()
        
        
        
        # await asyncio.sleep(5)

        
        larvae = self.units(LARVA)
        hatches = self.townhalls
        hq = self.townhalls.first

        # morph overlords
        if (self.supply_left < self.OVERLORD_CHECK) and (self.already_pending(OVERLORD) < self.OVERLORD_MORPH_LIMIT):
            if self.can_afford(OVERLORD) and larvae.exists:
                await self.do(larvae.random.train(OVERLORD))

        # morph drones
        
        # print('already_pending: {0} larvae.amount: {1} larvae.ready.amount: {2} minerals: {3}'.format(self.already_pending(DRONE), larvae.amount, larvae.ready.amount, self.minerals))
        if self.worker_production_allowed and (self.workers.amount + self.already_pending(DRONE) < self.DRONE_LIMIT):
            if self.already_pending(DRONE) < 1:
                if self.supply_left >= self.OVERLORD_CHECK or self.already_pending(OVERLORD):
                    if self.can_afford(DRONE) and larvae.amount > 0:
                        # larva = larvae.take(2)
                        await self.do(larvae.random.train(DRONE))

        
        # morph queens
        if self.units(SPAWNINGPOOL).ready.exists:
            if (self.units(QUEEN).amount + self.already_pending(QUEEN) < self.townhalls.amount):
                for hatch in self.townhalls.ready.noqueue:
                    if self.can_afford(QUEEN) and self.supply_left > 0:
                        await self.do(hatch.train(QUEEN))
                        # self.queen_pairs["hatch1"] = "queen1"


    # build buildings
    async def build_structures(self):
        larvae = self.units(LARVA)
        hq = self.townhalls.first

        # 17 hatch
        # first expansion: move worker, wait until enough minerals to build hatch
        if self.supply_used > 16 and self.townhalls.amount < 2:
            if not self.already_pending(HATCHERY) and self.next_expansion_location is None:
                self.worker_production_allowed = False
                self.next_expansion_location = await self.get_next_expansion()
                drone = self.select_build_worker(self.next_expansion_location)
                await self.do(drone.move(self.next_expansion_location))
                
        if self.next_expansion_location is not None:
            if self.can_afford(HATCHERY):
                self.worker_production_allowed = False
                await self.expand_now()
                self.next_expansion_location = None
                
        if self.already_pending(HATCHERY):
            self.DRONE_MORPH_LIMIT = 1

        # 17 extractor
        if self.supply_used > 16 and self.units(EXTRACTOR).amount < 1:
            if (self.already_pending(HATCHERY) + self.units(HATCHERY).amount) > 1:
                if not self.already_pending(EXTRACTOR) and self.can_afford(EXTRACTOR):
                    self.worker_production_allowed = False
                    drone = self.select_build_worker(hq.position)
                    target = self.state.vespene_geyser.closest_to(drone)
                    await self.do(drone.build(EXTRACTOR, target))
                if self.already_pending(EXTRACTOR):
                    self.DRONE_MORPH_LIMIT = 1

        # 17 pool             
        if self.supply_used > 16 and not self.units(SPAWNINGPOOL).exists:
            if (self.already_pending(HATCHERY) + self.units(HATCHERY).amount) > 1:
                if not self.already_pending(SPAWNINGPOOL) and self.can_afford(SPAWNINGPOOL):
                    self.worker_production_allowed = False
                    await self.build(SPAWNINGPOOL, near=hq)
                if self.already_pending(SPAWNINGPOOL):
                    self.DRONE_MORPH_LIMIT = 2
        
        # roach warren
        if self.supply_used > 43 and not self.units(ROACHWARREN).exists and not self.already_pending(ROACHWARREN):
            if self.can_afford(ROACHWARREN):
                self.worker_production_allowed = False
                await self.build(ROACHWARREN, near=hq)

        # 2x evo chamber
        if self.supply_used > 60 and (self.units(EVOLUTIONCHAMBER).amount + self.already_pending(EVOLUTIONCHAMBER)) < 2:
            if self.can_afford(EVOLUTIONCHAMBER):
                self.worker_production_allowed = False
                self.roach_production_allowed = False
                await self.build(EVOLUTIONCHAMBER, near=hq)

    async def scout(self):

        zerglings = self.units(ZERGLING)
        if zerglings.amount > 3:
            for zergling in zerglings:
                i = 0
                await self.do(zergling.move(self.enemy_start_locations[i]))
                i = i + 1


    async def expand(self):
        # future expansion
        if self.supply_used > 25 and (self.workers.amount > self.townhalls.amount * 20):
            if not self.already_pending(HATCHERY) and self.can_afford(HATCHERY):
                await self.expand_now()

        if self.supply_used > 43:
            if (self.units(EXTRACTOR).amount + self.already_pending(EXTRACTOR)) < self.townhalls.ready.amount * 2:
                for hatch in self.townhalls.ready:
                    vespenes = self.state.vespene_geyser.closer_than(10, hatch)
                    for vespene in vespenes:
                        if self.can_afford(EXTRACTOR):
                            drone = self.select_build_worker(vespene.position)
                            if drone is not None:
                                await self.do(drone.build(EXTRACTOR, vespene))


    async def upgrade(self):
        # metabolic boost
        if not self.metabolic_boost and self.units(SPAWNINGPOOL).ready.exists:
            sp = self.units(SPAWNINGPOOL)
            if self.can_afford(UpgradeId.ZERGLINGMOVEMENTSPEED):
                self.metabolic_boost = True
                await self.do(sp.first(RESEARCH_ZERGLINGMETABOLICBOOST))

        # overlord speed
        if not self.overlord_speed and self.supply_used > 31 and self.units(HATCHERY).idle.exists:
            if self.can_afford(AbilityId.RESEARCH_PNEUMATIZEDCARAPACE):
                hatch = self.units(HATCHERY).idle.random
                self.overlord_speed = True
                await self.do(hatch(RESEARCH_PNEUMATIZEDCARAPACE))

        # lair
        if self.supply_used > 43:
            if not self.already_pending(LAIR) and self.units(SPAWNINGPOOL).ready.exists and (self.units(LAIR).amount <= 0):
                if self.can_afford(LAIR) and self.units(HATCHERY).ready.idle.exists:
                    hq = self.townhalls.first
                    await self.do(hq(UPGRADETOLAIR_LAIR))

        # roach speed
        if not self.roach_speed and self.supply_used > 61 and self.units(ROACHWARREN).ready.idle.exists:
            if self.can_afford(AbilityId.RESEARCH_GLIALREGENERATION):
                warren = self.units(ROACHWARREN).ready.idle.random
                self.roach_speed = True
                await self.do(warren(RESEARCH_GLIALREGENERATION))
        
        # upgrades
        if self.units(EVOLUTIONCHAMBER).ready.idle.exists:
            evo = self.units(EVOLUTIONCHAMBER).ready.idle.random
            abilities = await self.get_available_abilities(evo)
            if RESEARCH_ZERGMISSILEWEAPONSLEVEL1 in abilities and self.can_afford(RESEARCH_ZERGMISSILEWEAPONSLEVEL1):
                await self.do(evo(RESEARCH_ZERGMISSILEWEAPONSLEVEL1))
            if RESEARCH_ZERGGROUNDARMORLEVEL1 in abilities and self.can_afford(RESEARCH_ZERGGROUNDARMORLEVEL1):
                await self.do(evo(RESEARCH_ZERGGROUNDARMORLEVEL1))

    async def build_army(self):
        larvae = self.units(LARVA)

        # scouts
        # if self.supply_used > 25 and self. supply_used < 30 and self.units(SPAWNINGPOOL).ready.exists and self.units(ZERGLING).amount < 1:
        #     if self.can_afford(ZERGLING) and larvae.exists:
        #         await self.do(larvae.random.train(ZERGLING))

        # main roach force
        if self.roach_production_allowed and self.units(ROACHWARREN).ready.exists and self.workers.amount > 45:
            if self.already_pending(ROACH) < (larvae.amount + self.units(EGG).amount) * 0.75:
                if self.supply_left >= self.OVERLORD_CHECK or self.already_pending(OVERLORD):
                    if self.can_afford(ROACH) and larvae.exists:
                        await self.do(larvae.random.train(ROACH))




    async def attack(self):
        # zerglings = self.units(ZERGLING)
        # if self.first_wave is False:
        #     if zerglings.amount > 16:
        #         self.first_wave = True
        #         firstZerglingWave = self.units(ZERGLING)

        # if self.first_wave:
        #     for zergling in zerglings:
        #         await self.do(zergling.attack(self.enemy_start_locations[0]))
                # zerglings = self.units(ZERGLING)

        roaches = self.units(ROACH)
        if self.known_enemy_structures.exists:
            target = (self.known_enemy_structures).random.position
        else:
            target = self.enemy_start_locations[0]

        # if target == self.enemy_start_locations[0] and roaches.idle.amount > 5:
        #     target = 

        # if self.wave == 0 and roaches.idle.amount > 25:
        #     self.wave = self.wave + 1
        #     for roach in roaches.idle:
        #         await self.do(roach.attack(target))
        # elif self.wave >= 1 and roaches.idle.amount > 35:
        #     self.wave = self.wave + 1
        #     for roach in roaches.idle:
        #         await self.do(roach.attack(target))
        # elif self.wave >= 1 and roaches.closer_than(50, self.enemy_start_locations[0]).amount > 35:
        #     for roach in roaches.idle:
        #         await self.do(roach.attack(target))
        # elif self.wave >= 1 and roaches.closer_than(50, self.enemy_start_locations[0]).amount < 35:

        if self.wave == 0 and self.supply_used > 150:
            self.wave = self.wave + 1
            for roach in roaches.idle:
                await self.do(roach.attack(target))
        elif self.wave >= 1 and roaches.idle.amount > 35:
            self.wave = self.wave + 1
            for roach in roaches.idle:
                await self.do(roach.attack(target))
        elif self.wave >= 1 and roaches.closer_than(50, self.enemy_start_locations[0]).amount > 35:
            for roach in roaches.idle:
                await self.do(roach.attack(target))

    async def defend(self):
        if self.known_enemy_units.closer_than(20, self.start_location).amount > 1:
            # self.worker_production_allowed = False
            if self.units.of_type([ZERGLING, ROACH, HYDRALISK, BROODLORD]).amount > 0:
                defenders = self.units.of_type([ZERGLING, ROACH, HYDRALISK, BROODLORD])
                for defender in defenders.idle:
                    await self.do(defender.attack(self.known_enemy_units.closer_than(20, self.start_location)))
                



    # check when to build overlords
    async def check_overlord(self):
        if self.supply_used > 70:
            self.OVERLORD_CHECK = 13
            self.OVERLORD_MORPH_LIMIT = 4
        elif self.supply_used > 50:
            self.OVERLORD_CHECK = 9
            self.OVERLORD_MORPH_LIMIT = 3
        elif self.supply_used > 40:
            self.OVERLORD_CHECK = 7
            self.OVERLORD_MORPH_LIMIT = 2
        elif self.supply_used > 30:
            self.OVERLORD_CHECK = 6
            self.OVERLORD_MORPH_LIMIT = 2
        elif self.supply_used > 20:
            self.OVERLORD_CHECK = 4

    # queen injections
    async def queen_inject(self):
        queens = self.units(QUEEN)
        if queens.amount > 0:
            for hatch in self.townhalls:
                if queens.idle.exists:
                    queen = queens.idle.closest_to(hatch)
                    abilities = await self.get_available_abilities(queen)
                    if AbilityId.EFFECT_INJECTLARVA in abilities:
                        await self.do(queen(AbilityId.EFFECT_INJECTLARVA, hatch))

def main():
    run_game(maps.get("AbyssalReefLE"),[Bot(Race.Zerg, ZergBot()), Computer(Race.Random, Difficulty.Harder)], realtime=False)

if __name__ == '__main__':
    main()
