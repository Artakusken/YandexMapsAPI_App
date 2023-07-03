import pygame
import pygame_gui
from requests import get
from os import remove
from sys import exit
from math import radians, cos


class Map:
    """ A map object, with certain params, that are required for the api request """
    def __init__(self, lonlat: str, map_type: int, zoom: int):
        self.longitude = float(lonlat.split()[0])
        self.latitude = float(lonlat.split()[1])
        self.pt_longitude = 0
        self.pt_latitude = 0
        self.map_types = {0: "sat", 1: "map", 2: "sat,skl"}
        self.l = map_type
        self.zoom = zoom

    def get_map_params(self, params_type: int) -> dict[str, any]:
        if params_type == 1:  # no pointer
            params = {"ll": f"{self.longitude},{self.latitude}",
                      "l": self.map_types[self.l % 3],
                      "z": self.zoom,
                      "size": "650,450"}
        else:  # with pointer (key "pt")
            params = {"ll": f"{self.longitude},{self.latitude}",
                      "pt": f"{self.pt_longitude},{self.pt_latitude}",
                      "l": self.map_types[self.l % 3],
                      "z": self.zoom,
                      "size": "650,450"}

        return params


def get_map_image(map_object: Map) -> pygame.Surface:
    """ Makes a request to get a map image. The result depends on the map parameters """
    global POINTER_ON_MAP

    static_map = "https://static-maps.yandex.ru/1.x/"
    if not POINTER_ON_MAP:
        map_response = get(static_map, params=map_object.get_map_params(1))
    else:
        map_response = get(static_map, params=map_object.get_map_params(2))

    if map_response:  # write bytes to a png file, this file is map image
        with open("map.png", "wb") as map_file:
            map_file.write(map_response.content)
        return pygame.image.load("map.png")
    else:
        print("Ошибка выполнения запроса:")
        print(map_response)
        print("Http статус:", map_response.status_code, "(", map_response.reason, ")")
        exit(1)


def find_map_object_coords(name: str) -> list[float]:
    """ Returns the geographical coordinates (longitude, latitude) of the searched location """
    response = get(f"http://geocode-maps.yandex.ru/1.x/?apikey={GEOCODER_APIKEY}={name}&format=json")
    if response:
        json_data = response.json()
        if json_data["response"]["GeoObjectCollection"]["metaDataProperty"]["GeocoderResponseMetaData"]["found"] != '0':
            return [float(i) for i in
                    json_data["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"].split()]
    return [map_data.longitude, map_data.latitude]


def get_address(name: str) -> str:
    """ Returns the address string of some place """
    response = get(f"http://geocode-maps.yandex.ru/1.x/?apikey={GEOCODER_APIKEY}&geocode={name}&format=json")
    if response:
        json_data = response.json()
        if json_data["response"]["GeoObjectCollection"]["metaDataProperty"]["GeocoderResponseMetaData"]["found"] != '0':
            address = json_data["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["metaDataProperty"]["GeocoderMetaData"]['Address']["formatted"]
            if POST_ADDRESS_ON and "postal_code" in json_data["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["metaDataProperty"]["GeocoderMetaData"]['Address'].keys():
                address += "; " + json_data["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["metaDataProperty"]["GeocoderMetaData"]['Address']['postal_code']
            return address
    return ""


def draw_text(surf: pygame.display, text: pygame.Surface, x: int, y: int) -> None:
    """ Draws a line of text in the specified coordinates """
    text_rect = text.get_rect()
    text_rect.midtop = (x, y)
    surf.blit(text, text_rect)


def on_mouse_click(mouse_pos: list[float], click_type: int) -> pygame.Surface:
    """ 
        Sets a new map image when the user clicks on the map image (the clicked point becomes the middle of a map).
        If the right button was clicked, the function also finds organizations (activates find_map_object(True))
    """
    global POINTER_ON_MAP

    off_x = mouse_pos[0] - 325
    off_y = 225 - mouse_pos[1]
    map_data.pt_longitude = map_data.longitude + off_x * OFFSET_IN_DEGREES * 2 ** (15 - map_data.zoom)
    map_data.pt_latitude = map_data.latitude + off_y * OFFSET_IN_DEGREES * 2 ** (15 - map_data.zoom) * cos(radians(map_data.latitude))
    POINTER_ON_MAP = True

    if click_type == 1:
        find_map_object()
    else:
        find_map_object(True)

    return get_map_image(map_data)


def find_map_object(org: bool = False) -> None:
    """ Fills address_field with the address of the place located in map_data coordinates """
    response = get(f"http://geocode-maps.yandex.ru/1.x/?apikey={GEOCODER_APIKEY}&geocode={map_data.pt_longitude},{map_data.pt_latitude}&format=json")
    if response:
        json_response = response.json()
        map_object = json_response["response"]["GeoObjectCollection"]["featureMember"]
        if map_object:
            map_data.longitude = map_data.pt_longitude
            map_data.latitude = map_data.pt_latitude
            object_name = map_object[0]["GeoObject"]["metaDataProperty"]["GeocoderMetaData"]["text"]

            if org:
                address_field.set_text(find_organisation(object_name))
            else:
                address_field.set_text(get_address(object_name))


def find_organisation(name: str = "Магазин") -> str:
    """ Returns the name of the nearest business (if one exists) """
    search_api_server = "https://search-maps.yandex.ru/v1/"
    search_params = {
        "apikey": SEARCH_APIKEY,
        "lang": "ru_RU",
        "ll": f"{map_data.pt_longitude},{map_data.pt_latitude}",
        "spn": "0.1,0.1",
        "type": "biz",
        "text": name
    }
    response = get(search_api_server, params=search_params)
    if not response:
        raise RuntimeError(
            f"""Ошибка выполнения запроса:
            {search_api_server}
            Http статус: {response.status_code} ({response.reason})""")

    json_response = response.json()
    organizations = json_response["features"]
    if organizations:
        org = organizations[0]  # pick the first organization from the list
        if lonlat_distance([float(i) for i in org["geometry"]["coordinates"]], [map_data.pt_longitude, map_data.pt_latitude]) <= 50:
            return org["properties"]["CompanyMetaData"]["name"] + "; " + org["properties"]["CompanyMetaData"]["address"]
    return "Компании в округе не найдены"


def lonlat_distance(a: list[float], b: list[float]) -> float:
    """ Calculates the distance (in km) between two points using their geographical coordinates (longitude, latitude) """
    degree_to_meters_factor = 111 * 1000
    a_lon, a_lat = a
    b_lon, b_lat = b

    radians_latitude = radians((a_lat + b_lat) / 2.)
    lat_lon_factor = cos(radians_latitude)

    dx = abs(a_lon - b_lon) * degree_to_meters_factor * lat_lon_factor
    dy = abs(a_lat - b_lat) * degree_to_meters_factor

    distance = 0.5 ** (dx * dx + dy * dy)

    return round(distance, 3)


# Pygame, screen and font initialization
pygame.init()
screen = pygame.display.set_mode((1050, 550))
pygame.display.set_caption("Useless map app")
clock = pygame.time.Clock()
text_font = pygame.font.Font(pygame.font.match_font('arial'), 25)

# Initialization of gui manager and its buttons/TextEntryLines
gui_manager = pygame_gui.UIManager((1050, 650))
entry_object = pygame_gui.elements.UITextEntryLine(relative_rect=pygame.Rect((660, 50), (380, 40)), manager=gui_manager)
search_btn = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((660, 92), (120, 25)), text="Искать", manager=gui_manager)
clear_btn = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((780, 92), (120, 25)), text="Очистить", manager=gui_manager)
address_field = pygame_gui.elements.UITextEntryLine(relative_rect=pygame.Rect((10, 500), (644, 40)), manager=gui_manager)

# Make address_field unable to interact, this is only for data output
address_field.is_enabled = False
address_field.remove_element_from_focus_set(address_field)

# Globals
COORD_DIFF = 0.005
OFFSET_IN_DEGREES = 0.0000428
GEOCODER_APIKEY = "You need to get it"  # https://yandex.ru/dev/maps/geocoder
SEARCH_APIKEY = "You need to get it"  # https://yandex.ru/dev/maps/geosearch
APP_IS_ON = True
POINTER_ON_MAP = False
POST_ADDRESS_ON = False
map_data = Map("20.5 54.72", 1, 12)
CURR_IMG = get_map_image(map_data)

# Text strings
postal_code_on = text_font.render("Почтовый индекс: показывать", True, (220, 220, 220))
postal_code_off = text_font.render("Почтовый индекс: не показывать", True, (220, 220, 220))
scheme_map = text_font.render("Тип: Карта", True, (220, 220, 220))
physical_roads_map = text_font.render("Тип: Спутник, дороги", True, (220, 220, 220))
physical_map = text_font.render("Тип: Спутник", True, (220, 220, 220))
map_types_naming = {0: (physical_map, 723), 1: (scheme_map, 711), 2: (physical_roads_map, 760)}
instruction_map_type0 = text_font.render("Смена типа карты:", True, (220, 220, 220))
instruction_map_type1 = text_font.render("Q, RCTRL", True, (220, 220, 220))
instruction_zooming0 = text_font.render("Приближение:", True, (220, 220, 220))
instruction_zooming1 = text_font.render("+, -, PageUP, PageDown, колесо", True, (220, 220, 220))
instruction_moving0 = text_font.render("Передвижение:", True, (220, 220, 220))
instruction_moving1 = text_font.render("WASD, стрелочки, клик мыши", True, (220, 220, 220))


while APP_IS_ON:  # app loop

    # draw map image, text, ui

    screen.fill((0, 0, 0))  # background
    if POST_ADDRESS_ON:  # line about postal code
        draw_text(screen, postal_code_on, 154, 460)
    else:
        draw_text(screen, postal_code_off, 168, 460)
    # draw all text line (they're always same)
    draw_text(screen, map_types_naming[map_data.l % 3][0], map_types_naming[map_data.l % 3][1], 10)
    draw_text(screen, instruction_moving0, 730, 200)
    draw_text(screen, instruction_moving1, 800, 230)
    draw_text(screen, instruction_map_type0, 745, 280)
    draw_text(screen, instruction_map_type1, 707, 310)
    draw_text(screen, instruction_zooming0, 727, 360)
    draw_text(screen, instruction_zooming1, 812, 390)
    # blit map image
    screen.blit(CURR_IMG, (0, 0))
    # gui_manager draw all ui elements
    gui_manager.update(clock.tick(30) / 1000.0)
    gui_manager.draw_ui(screen)

    # check all possible events
    for event in pygame.event.get():
        # when mouse hoover map image, scrolling works
        if event.type == pygame.MOUSEWHEEL and 0 < pygame.mouse.get_pos()[0] < 650 and 0 < pygame.mouse.get_pos()[1] < 450:
            if 2 < map_data.zoom + event.y < 21:
                map_data.zoom += event.y
            if map_data.zoom + event.y < 2:
                map_data.zoom = 2
            if map_data.zoom + event.y > 21:
                map_data.zoom = 21
            CURR_IMG = get_map_image(map_data)  # new image

        if event.type == pygame.KEYDOWN:  # check keyboard keys
            
            if event.key == pygame.K_ESCAPE:
                APP_IS_ON = False

            if event.key == pygame.K_PAGEUP or ((event.key == pygame.K_EQUALS or event.key == pygame.K_KP_PLUS) and not entry_object.cursor_on):
                if map_data.zoom < 18:
                    map_data.zoom += 1
                    CURR_IMG = get_map_image(map_data)  # new image

            if event.key == pygame.K_PAGEDOWN or ((event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS) and not entry_object.cursor_on):
                if map_data.zoom > 1:
                    map_data.zoom -= 1
                    CURR_IMG = get_map_image(map_data)  # new image

            if (event.key == pygame.K_LEFT or event.key == pygame.K_a) and not entry_object.cursor_on:
                map_data.longitude -= COORD_DIFF * 2 ** (15 - map_data.zoom)
                if map_data.longitude < -180:
                    map_data.longitude = 180 + (map_data.longitude + 180)
                CURR_IMG = get_map_image(map_data)  # new image

            if (event.key == pygame.K_RIGHT or event.key == pygame.K_d) and not entry_object.cursor_on:
                map_data.longitude += COORD_DIFF * 2 ** (15 - map_data.zoom)
                if map_data.longitude > 180:
                    map_data.longitude = -180 + (map_data.longitude - 180)
                CURR_IMG = get_map_image(map_data)  # new image

            if (event.key == pygame.K_UP or (event.key == pygame.K_w and not entry_object.cursor_on)) and map_data.latitude < 85:
                delta = COORD_DIFF * 0.7 * 2 ** (15 - map_data.zoom)
                if map_data.latitude + delta < 85:
                    map_data.latitude += delta
                else:
                    map_data.latitude = 85
                CURR_IMG = get_map_image(map_data)  # new image

            if (event.key == pygame.K_DOWN or (event.key == pygame.K_s and not entry_object.cursor_on)) and map_data.latitude > -85:
                delta = COORD_DIFF * 0.7 * 2 ** (15 - map_data.zoom)
                if map_data.latitude - delta > -85:
                    map_data.latitude -= delta
                else:
                    map_data.latitude = -85
                CURR_IMG = get_map_image(map_data)  # new image

            if event.key == pygame.K_RCTRL or (event.key == pygame.K_q and not entry_object.cursor_on):
                map_data.l += 1
                CURR_IMG = get_map_image(map_data)  # new image

            if event.key == pygame.K_RETURN and entry_object.cursor_on:  # new map, when something is being searched for
                POINTER_ON_MAP = True  # pointer points the place
                entry_object.unfocus()  # lift off mouse from text input, preventing typing enter in text
                map_data.longitude, map_data.latitude = find_map_object_coords(entry_object.text)
                map_data.pt_longitude, map_data.pt_latitude = find_map_object_coords(entry_object.text)
                searched_place = get_address(entry_object.text)
                if searched_place:
                    address_field.set_text(searched_place)
                else:
                    address_field.set_text("Не найдено")
                CURR_IMG = get_map_image(map_data)  # new image
                entry_object.focus()

        gui_manager.process_events(event)
        if event.type == pygame_gui.UI_BUTTON_PRESSED:  # check ui button events
            
            if event.ui_element.text == "Искать":  # new map, when something is being searched for
                map_data.longitude, map_data.latitude = find_map_object_coords(entry_object.text)
                map_data.pt_longitude, map_data.pt_latitude = find_map_object_coords(entry_object.text)
                address_field.set_text(get_address(entry_object.text))
                POINTER_ON_MAP = True
                CURR_IMG = get_map_image(map_data)  # new image
                
            if event.ui_element.text == "Очистить":  # clear TextEntryLine (address_field and entry_object)
                POINTER_ON_MAP = False
                address_field.set_text("")
                entry_object.set_text("")
                CURR_IMG = get_map_image(map_data)  # new image

        if event.type == pygame.MOUSEBUTTONDOWN:  # check mouseclick
            x, y = pygame.mouse.get_pos()
            # if mouse is clicked over the postal_code_on/off-line, it switches
            if 20 < x < 350 and 450 < y < 490:
                if POST_ADDRESS_ON:
                    POST_ADDRESS_ON = False
                    if len(address_field.text) > 0:
                        address_field.set_text(get_address(address_field.text))
                    elif len(entry_object.text) > 0:
                        address_field.set_text(get_address(entry_object.text))
                else:
                    POST_ADDRESS_ON = True
                    if len(address_field.text) > 0:
                        address_field.set_text(get_address(address_field.text))
                    elif len(entry_object.text) > 0:
                        address_field.set_text(get_address(entry_object.text))
            # if mouse is clicked while hovering over the map, the point becomes the middle of the map image
            if 0 < x < 650 and 0 < y < 450:
                if event.button == 1:
                    CURR_IMG = on_mouse_click(event.pos, 1)  # new image, with the address of a point
                if event.button == 3:
                    CURR_IMG = on_mouse_click(event.pos, 2)  # new image, with the address of the nearest biz
                    entry_object.set_text("")
                    
        if event.type == pygame.QUIT:
            APP_IS_ON = False
            
    pygame.display.update()
    clock.tick(30)

remove("map.png")  # delete map image file
