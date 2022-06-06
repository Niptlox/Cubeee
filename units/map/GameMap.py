import glob
import pickle

from noise import snoise2 as pnoise2

from units.Creatures import Slime, Cow, Wolf, SlimeBigBoss, Snake
from units.Entity import PhysicalObject
from units.Items import ItemsTile
from units.TilesClass import Chest
from units.Tools import TOOLS
from units.biomes import biome_of_pos
from ..Tiles import *


class GameMap:
    save_slots = 16

    def __init__(self, game, generate_type, base_generation=None) -> None:
        self.game = game
        self.gen_type = generate_type
        self.tile_data_size = 4
        self.map_size = [-1, -1]
        self.chunk_arr_width = CHUNK_SIZE * self.tile_data_size
        self.chunk_arr_size = self.tile_data_size * CHUNK_SIZE ** 2
        self.game_map = {}
        self.base_generation = base_generation
        self.num_save_map = 0
        self.saved = False
        if self.base_generation is None:
            self.new_base_generation()

    def new_base_generation(self):
        self.base_generation = random.randint(-1e5, 1e5)
        print("base_generation", self.base_generation)

    def set_vars(self, vrs):
        # convert dynamic objs
        for pos, chunk in vrs["game_map"].items():
            for i in range(len(chunk[1])):
                type_obj, vrs_obj = chunk[1][i]
                obj: PhysicalObject = type_obj(self.game)
                obj.set_vars(vrs_obj)
                chunk[1][i] = obj
        # set vars
        for k, i in vrs.items():
            self.__dict__[k] = i

    def get_vars(self):
        d = self.__dict__.copy()
        ch = d["game_map"][-1, -1]
        print("==", d["game_map"][-1, -1])
        # === convert dynamic_objs ===
        game_map = {}
        for pos, chunk in d["game_map"].items():
            game_map[pos] = chunk.copy()
            game_map[pos][1] = [(type(obj), obj.get_vars()) for obj in chunk[1]]
        d["game_map"] = game_map
        d.pop("game")
        return d

    def chunk(self, xy, default=None, for_player=False, create_chunk=False):
        res = self.game_map.get(xy, default)
        if res is default and create_chunk:
            res = self.generate_chunk(*xy)
        if res and for_player:
            crt_cash = res[3]
            if self.game.tact > crt_cash[2] + FPS * 300:
                if crt_cash[1] < CHUNK_CREATURE_LIMIT:
                    crt_cash[2] = self.game.tact
                    dynamic_tiles = res[1]
                    scroll = self.game.screen_map.scroll
                    # if not self.game.screen_map.display_rect.collidepoint(x - scroll[0], y - scroll[1]):
                    crt_cnt = min(len(crt_cash[0]), random.randint(0, CHUNK_CREATURE_LIMIT - crt_cash[1]))
                    tiles_xy = random.choices(tuple(crt_cash[0]), k=crt_cnt)
                    for tile_xy in tiles_xy:
                        # if random.random() < 0.005:
                            x, y = tile_xy[0] * TSIZE, tile_xy[1] * TSIZE
                            Crt = random_creature_selection()
                            if Crt is not None:
                                dynamic_tiles.append(Crt(self.game, (x, y)))
                                crt_cash[1] += 1
        return res

    def chunk_gen(self, xy):
        index = 0
        chunk = self.chunk(xy)
        for y in range(CHUNK_SIZE):
            for x in range(CHUNK_SIZE):
                yield index, y, x, chunk[0][index:index + self.tile_data_size]
                index += self.tile_data_size

    def index_gen(self):
        index = 0
        while index < self.chunk_arr_size:
            yield index
            index += self.tile_data_size

    @staticmethod
    def to_chunk_xy(x, y):
        return x // CHUNK_SIZE, y // CHUNK_SIZE

    @staticmethod
    def to_tile_xy(x, y):
        return x // TSIZE, y // TSIZE

    def get_tile_climate(self, x, y):
        chunk = self.chunk(self.to_chunk_xy(x, y))
        if chunk is None:
            return
        return chunk[4][(y % CHUNK_SIZE) * CHUNK_SIZE + (x % CHUNK_SIZE)]

    def get_static_tile(self, x, y, default=None, create_chunk=False):
        chunk = self.chunk(self.to_chunk_xy(x, y), create_chunk=create_chunk)
        if chunk is None:
            return default
        i = self.convert_pos_to_i(x, y)
        return chunk[0][i:i + self.tile_data_size]

    def get_static_tile_type(self, x, y, default=None, create_chunk=True):
        chunk = self.chunk((x // CHUNK_SIZE, y // CHUNK_SIZE), create_chunk=create_chunk)
        if chunk is None:
            return default
        i = self.convert_pos_to_i(x, y)
        return chunk[0][i]

    def set_static_tile(self, x, y, tile, create_chunk=True):
        chunk = self.chunk((x // CHUNK_SIZE, y // CHUNK_SIZE), create_chunk=create_chunk)
        if chunk is not None:
            if tile is None:
                tile = [0, 0, 0, 0]
            i = self.convert_pos_to_i(x, y)
            chunk[0][i:i + self.tile_data_size] = tile
            return True
        return False

    def set_static_tile_group(self, x, y, group_id):
        chunk = self.chunk((x // CHUNK_SIZE, y // CHUNK_SIZE))
        if chunk is not None:
            i = self.convert_pos_to_i(x, y)
            chunk[0][i + 3] = group_id
            return True
        return False

    def set_static_tile_solidity(self, x, y, sol):
        """Установить прочность тайла"""
        chunk = self.chunk((x // CHUNK_SIZE, y // CHUNK_SIZE))
        if chunk is not None:
            i = self.convert_pos_to_i(x, y)
            chunk[0][i + 1] = sol
            return True
        return False

    def set_static_tile_state(self, x, y, state):
        chunk = self.chunk((x // CHUNK_SIZE, y // CHUNK_SIZE))
        if chunk is not None:
            i = self.convert_pos_to_i(x, y)
            chunk[0][i + 2] = state
            return True
        return False

    def move_dinamic_obj(self, chunk_x, chunk_y, new_chunk_x, new_chunk_y, obj):
        # print(chunk_x, chunk_y, new_chunk_x, new_chunk_y, obj)
        chunk = self.chunk((new_chunk_x, new_chunk_y))
        if not chunk:
            chunk = self.generate_chunk(new_chunk_x, new_chunk_y)
        ochunk = self.chunk((chunk_x, chunk_y))
        if ochunk is not None and obj in ochunk[1]:
            ochunk[1].remove(obj)
            chunk[1].append(obj)
            if obj.class_obj & OBJ_CREATURE:
                ochunk[3][1] -= 1
                chunk[3][1] += 1
            return True
        else:
            obj.sprite.blit(pg.Surface((10, 10)), (0, 0))
            print(f"Ошибка передвижения динамики. Объект {obj} не находится в чанке {(chunk_x, chunk_y)}")
            # raise Exception(f"Ошибка передвижения динамики. Объект {obj} не находится в чанке {(chunk_x, chunk_y)}")

        return

    def move_group_obj(self, chunk_x, chunk_y, new_chunk_x, new_chunk_y, obj):
        chunk = self.chunk((new_chunk_x, new_chunk_y))
        i = obj.id
        if chunk:
            ochunk = self.chunk((chunk_x, chunk_y))
            if ochunk is not None and i in ochunk[2]:
                del ochunk[2][i]
                chunk[2][i] = obj
                return True
            else:
                raise Exception(
                    f"Ошибка передвижения динамики. Объект {i, obj} не находится в чанке {(chunk_x, chunk_y)}")
            # return False
        return

    def del_group_obj(self, chunk_x, chunk_y, obj):
        chunk = self.chunk((chunk_x, chunk_y))
        i = obj.id
        if chunk and i in chunk[2]:
            del chunk[2][i]
            return True
        return False

    def add_group_obj(self, chunk_x, chunk_y, obj):
        chunk = self.chunk((chunk_x, chunk_y))
        if chunk:
            chunk[2][obj.id] = obj
            return True
        return False

    def del_dinamic_obj(self, chunk_x, chunk_y, obj):
        chunk = self.chunk((chunk_x, chunk_y))
        if chunk:
            if obj in chunk[1]:
                chunk[1].remove(obj)
                if obj.class_obj & OBJ_CREATURE:
                    chunk[3][1] -= 1
            else:
                print("Error !!! del_dinamic_obj", (chunk_x, chunk_y), obj)
            return True
        return False

    def add_dinamic_obj(self, chunk_x, chunk_y, obj):
        chunk = self.chunk((chunk_x, chunk_y))
        if chunk:
            if obj.class_obj & OBJ_CREATURE:
                chunk[3][1] += 1
            chunk[1].append(obj)
            return True
        return False

    def add_item_of_index(self, index, count_items, x, y):
        npos = (x * TSIZE + random.randint(0, TSIZE - HAND_SIZE), y * TSIZE)
        if index in TOOLS:
            # Инструмент
            item = TOOLS[index](self.game, pos=npos)
            item.set_owner(self)
        else:
            item = ItemsTile(self.game, index, npos, count_items)
        self.add_dinamic_obj(*self.to_chunk_xy(x, y), item)

    def convert_pos_to_i(self, x, y):
        # cx, cy = x % CHUNK_SIZE, y % CHUNK_SIZE
        # i = (cy * CHUNK_SIZE + cx) * self.tile_data_size
        return ((y % CHUNK_SIZE) * CHUNK_SIZE + (x % CHUNK_SIZE)) * self.tile_data_size

    @staticmethod
    def get_tile_ttile(ttile):
        """тип, прочность, состояние, переменная"""
        return [ttile, TILES_SOLIDITY.get(ttile, -1), 0, 0]

    def get_tile_ttile_tpos(self, ttile, tpos):
        """тип, прочность, состояние, переменная"""
        tile = self.get_tile_ttile(ttile)
        if tile[0] == 129:  # chest
            tile[3] = Chest(self.game, (tpos[0] * TSIZE, tpos[1] * TSIZE))
        return tile

    def create_pass_chunk(self, xy):
        """static tiles; dynamic tiles; group obj; creatures cash \
        (on graund tiles, cnt creatures, last tact generate); climate"""
        #                    0                          1   2   3              4
        self.game_map[xy] = [[0] * self.chunk_arr_size, [], {}, [set(), 0, 0], [0] * (CHUNK_SIZE ** 2)]
        return self.game_map[xy]

    def generate_chunk(self, x, y):
        if self.gen_type == TGENERATE_INFINITE_LANDS:
            return self.generate_chunk_noise_island(x, y)
        return

    def generate_chunk_noise_island(self, x, y):
        res = self.create_pass_chunk((x, y))
        static_tiles, dynamic_tiles, group_handlers, creature_cash, biome_info = res
        on_ground_tiles, cnt_creatures = creature_cash[0], creature_cash[1]
        tile_index = 0
        octaves = 6
        freq_x = 49 * 5
        freq_y = 14 * 5
        base = self.base_generation
        threshold = -0.3
        threshold = -0.2
        lacunarity = 2.4
        base_x = x * CHUNK_SIZE
        base_y = y * CHUNK_SIZE
        tile_y = base_y  # global tile y (not px)
        i = 0
        for y_pos in range(CHUNK_SIZE):  # local tile y in chunk (not px)
            tile_x = base_x  # global tile x (not px)
            for x_pos in range(CHUNK_SIZE):  # local tile x in chunk (not px)
                biome_info[i] = biome_of_pos(tile_x, tile_y)
                tile_type = None
                v = pnoise2(tile_x / freq_x, tile_y / freq_y, octaves, persistence=0.35, base=base,
                            lacunarity=lacunarity)
                if v < threshold:
                    v3 = pnoise2(tile_x / freq_x, (tile_y - 2 - random.randint(0, 1)) / freq_y, octaves,
                                 persistence=0.35, base=base, lacunarity=lacunarity)
                    if v3 < threshold:
                        tile_type = 3  # stone
                        v4 = pnoise2(tile_x / 10, tile_y / 10, 2, persistence=0.55, base=base, lacunarity=1)
                        if v4 < -0.7:
                            tile_type = 4  # blore
                        else:
                            v5 = pnoise2(tile_x / 16+100, tile_y / 16+100, 2, persistence=0.35, base=base + 1, lacunarity=1)
                            if v5 < -0.88:
                                tile_type = 5  # granite
                    else:
                        # v2 = pnoise2((tile_x + 1) / freq_x, (tile_y - 2 - random.randint(0, 1)) / freq_y, octaves,
                        #              persistence=0.35, base=base, lacunarity=lacunarity)
                        # if v2 < threshold:
                        tile_type = 2  # dirt
                        if (y_pos > 0 and static_tiles[tile_index - self.chunk_arr_width] == 0) or \
                                (y_pos == 0 and self.get_static_tile_type(tile_x, tile_y - 1, create_chunk=True) == 0):
                            tile_type = 1  # grass
                            if y_pos > 0:
                                on_ground_tiles.add((tile_x, tile_y))
                                plant_tile_type_state = random_plant_selection(biome_info[i][0])  # plant
                                if plant_tile_type_state is not None:
                                    plant_tile_type, state = plant_tile_type_state
                                    pl_i = tile_index - self.chunk_arr_width
                                    static_tiles[pl_i] = plant_tile_type
                                    static_tiles[pl_i + 1] = TILES_SOLIDITY.get(plant_tile_type, -1)
                                    static_tiles[pl_i + 2] = state
                                    if cnt_creatures < CHUNK_CREATURE_LIMIT:
                                        Crt = random_creature_selection()
                                        if Crt is not None:
                                            dynamic_tiles.append(Crt(self.game, (tile_x * TSIZE, tile_y * TSIZE)))
                                            cnt_creatures += 1
                else:
                    # пусто  
                    # ставим растение     
                    if y_pos == CHUNK_SIZE - 1 and \
                            self.get_static_tile(tile_x, tile_y + 1, default=0) == 1:
                        on_ground_tiles.add((tile_x, tile_y))
                        tile_type_state = random_plant_selection(biome_info[i][0])
                        if tile_type_state:
                            tile_type = tile_type_state[0]
                            static_tiles[tile_index + 2] = tile_type_state[1]
                if tile_index >= self.chunk_arr_size:
                    break
                if tile_type is not None:
                    static_tiles[tile_index] = tile_type
                    static_tiles[tile_index + 1] = TILES_SOLIDITY.get(tile_type, -1)
                tile_x += 1  # v28557
                tile_index += self.tile_data_size
                i += 1
            tile_y += 1
        creature_cash[1] = cnt_creatures
        return res

    def save_current_game_map(self):
        self.save_game_map(self.game, self.num_save_map)

    def save_game_map(self, game, num=0):
        self.saved = True
        self.game.ui.new_sys_message(f"Сохранение", draw_now=True)

        file_p = f'data/maps/game_map-{num}.pclv'
        print(f"GamaMap: '{file_p}' - SAVING...")
        self.num_save_map = num
        # try:
        data = {"game_map_vars": self.get_vars(), "player_vars": game.player.get_vars(),
                "game_version": GAME_VERSION, "game_tact": game.tact}
        t = pickle.dumps(data)
        with open(file_p, 'wb') as f:
            f.write(t)
        print("GamaMap - SAVE!")
        self.game.ui.new_sys_message(f"Карта сохранена #{num}", draw_now=True)
        # except Exception as exc:
        #     print("Ошибка сохранения:", exc)
        #     self.game.ui.new_sys_message(f"Ошибка {exc}")
        #     return False
        # finally:
        #
        #     return True

    def open_game_map(self, game, num=0):
        self.game.ui.new_sys_message(f"Загрузка карты #{num}", draw_now=True)

        file_p = f'data/maps/game_map-{num}.pclv'
        self.num_save_map = num
        print(f"GamaMap: '{file_p}' - LOADING...")
        # try:
        with open(file_p, 'rb') as f:
            data = pickle.load(f)
        version = data.get("game_version", "0.4")
        if version != GAME_VERSION:
            return
        game_map = data["game_map_vars"]
        game.game_map.set_vars(game_map)
        player = data["player_vars"]
        game.player.set_vars(player)
        game.tact = data.get("game_tact", 0)
        print(game.player.rect.center)
        if abs(game.player.rect.x) > 10000 or abs(game.player.rect.y) > 10000:
            game.screen_map.teleport_to_player()
        game.player.inventory.ui.redraw_top()
        # except Exception as exc:
        #     print("Ошибка загрузки:", exc)
        #     return False
        print("GamaMap - LOAD!")
        return file_p

    def get_list_maps(self):
        path = 'data/maps/'
        files = glob.glob(path + '*.pclv', recursive=False)
        return files

    def get_list_num_maps(self):
        files = self.get_list_maps()
        ar = [int(f.split("-")[1].split(".")[0]) for f in files if "None" not in f]
        return ar


def random_plant_selection(biome=None):
    if random.randint(0, 5) == 0:
        plants = {101: 0.1, 102: 0.1, 120: 0.05}
        if biome == 0:
            plants = {101: 0.1, 103: 0.1}
        plant_tile_type = random.choices(list(plants.keys()), list(plants.values()), k=1)[0]

        if plant_tile_type == 101:
            return plant_tile_type, random.randint(0, 3)
        if plant_tile_type == 102:
            if random.randint(0, 10) < 9:
                return plant_tile_type, 2  # вырастить мгновено дерево
        return plant_tile_type, 0
    return None


def grow_tree(pos, game_map: GameMap):
    woods = ((0, 0), (0, -1), (0, -2), (0, -3))
    leaves = ((-1, -1), (1, -1), (1, -2), (-1, -2), (1, -3), (-1, -3), (0, -4))
    x, y = pos
    for ax, ay in woods:
        game_map.set_static_tile(x + ax, y + ay, GameMap.get_tile_ttile(110))
    for ax, ay in leaves:
        if game_map.get_static_tile_type(x + ax, y + ay, default=0) == 0:
            game_map.set_static_tile(x + ax, y + ay, GameMap.get_tile_ttile(105))


def random_creature_selection():
    r = random.random()
    if r >= CHUNK_CREATURE_CHANCE:
        return None

    crt = random.choices([Slime, Cow, Snake, Wolf, SlimeBigBoss], [20, 5, 1, 0.7, 0.25], k=1)
    # print("random_creature_selection", crt)
    return crt[0]

# from collections import Counter
# Counter(random.choices(['Slime', 'Cow', 'Wolf', 'SlimeBigBoss'], [20, 5, 0.7, 0.25])[0]
#         for _ in range(100000))
# Counter({'Slime': 77209, 'Cow': 19239, 'Wolf': 2595, 'SlimeBigBoss': 957})
