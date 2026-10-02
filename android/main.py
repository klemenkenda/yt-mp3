"""YT to MP3 - Android app (Kivy). Shares the core pipeline with the desktop app (yt_mp3 package).

On a PC this also runs for UI development:  python android/main.py
"""
import os
import queue
import re
import sys
import tempfile
import time
from pathlib import Path

from kivy.utils import platform

ANDROID = platform == "android"
if not ANDROID:  # dev: use the package from ../src
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kivy.animation import Animation  # noqa: E402
from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.clipboard import Clipboard  # noqa: E402
from kivy.core.text import LabelBase  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.lang import Builder  # noqa: E402
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty  # noqa: E402
from kivy.storage.jsonstore import JsonStore  # noqa: E402
from kivy.uix.behaviors import ButtonBehavior  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.floatlayout import FloatLayout  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.modalview import ModalView  # noqa: E402
from kivy.uix.stencilview import StencilView  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402
from kivy.utils import get_color_from_hex  # noqa: E402

HERE = Path(__file__).resolve().parent
BITRATES = ("128", "192", "256", "320")
URL_RE = re.compile(r"https?://\S+")

# Material 3 dark color scheme (baseline seed #6750A4) + a green "success" role
M3 = {
    "primary": "#D0BCFF",
    "on_primary": "#381E72",
    "secondary_container": "#4A4458",
    "on_secondary_container": "#E8DEF8",
    "surface": "#141218",
    "surface_low": "#1D1B20",
    "surface_container": "#211F26",
    "surface_high": "#2B2930",
    "surface_highest": "#36343B",
    "on_surface": "#E6E0E9",
    "on_surface_variant": "#CAC4D0",
    "outline": "#938F99",
    "outline_variant": "#49454F",
    "error": "#F2B8B5",
    "on_error": "#601410",
    "success": "#7DD99B",
    "on_success": "#00391B",
}
C = {k: get_color_from_hex(v) for k, v in M3.items()}

# Material Icons font (Apache 2.0, github.com/google/material-design-icons)
LabelBase.register("Icons", str(HERE / "MaterialIcons-Regular.ttf"))
ICONS = {name: chr(cp) for name, cp in {
    "content_paste": 0xE14F, "close": 0xE5CD, "file_download": 0xE2C4, "library_music": 0xE030,
    "music_note": 0xE405, "folder": 0xE2C7, "arrow_back": 0xE5C4, "refresh": 0xE5D5,
}.items()}
STATUS_COLOR = {"queued": "on_surface_variant", "skipped": "on_surface_variant", "active": "primary",
                "done": "success", "error": "error"}

KV = "\n".join(f"#:set {k} {v!r}" for k, v in
               [*C.items(), ("ICONS", ICONS), ("ICON_PNG", str(HERE / "icon.png"))]) + """
#:import dp kivy.metrics.dp
#:import Window kivy.core.window.Window
#:import FadeTransition kivy.uix.screenmanager.FadeTransition

# -- buttons (pill shaped, 12% state layer while pressed) ----------------------

<FilledButton>:
    color: self.fg
    disabled_color: on_surface[:3] + [0.38]
    font_size: '15sp'
    bold: True
    size_hint_y: None
    height: dp(48)
    canvas.before:
        Color:
            rgba: on_surface[:3] + [0.12] if self.disabled else self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height / 2]
        Color:
            rgba: self.fg[:3] + [0.12 if self.state == 'down' else 0]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height / 2]
        Color:
            rgba: self.line
        Line:
            rounded_rectangle: self.x + dp(.5), self.y + dp(.5), self.width - dp(1), self.height - dp(1), self.height / 2 - dp(1)
            width: dp(1)

<OutlinedButton@FilledButton>:
    bg: [0, 0, 0, 0]
    fg: primary
    line: outline

<TextButton@FilledButton>:
    bg: [0, 0, 0, 0]
    fg: primary
    height: dp(40)

# assist chip with a leading icon
<Chip@ButtonBehavior+BoxLayout>:
    icon: ''
    text: ''
    size_hint: None, None
    size: self.minimum_width, dp(32)
    padding: dp(8), 0, dp(16), 0
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: on_surface[:3] + [0.12 if self.state == 'down' else 0]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]
        Color:
            rgba: outline_variant
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(8)
            width: dp(1)
    Icon:
        text: root.icon
        color: primary
        font_size: '18sp'
        size_hint_x: None
        width: dp(18)
    Label:
        text: root.text
        color: on_surface
        font_size: '14sp'
        size_hint_x: None
        width: self.texture_size[0]

<Icon@Label>:
    font_name: 'Icons'
    font_size: '24sp'

<IconButton@ButtonBehavior+Icon>:
    color: on_surface_variant
    size_hint: None, None
    size: dp(48), dp(48)
    canvas.before:
        Color:
            rgba: on_surface[:3] + [0.12 if self.state == 'down' else 0]
        Ellipse:
            pos: self.center_x - dp(20), self.center_y - dp(20)
            size: dp(40), dp(40)

# -- inputs --------------------------------------------------------------------

<OutlinedField>:
    field: ti
    size_hint_y: None
    height: dp(64)
    canvas.before:
        Color:
            rgba: primary if root.focused else outline
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height - dp(8), dp(4)
            width: dp(1.5) if root.focused else dp(1)
    Label:
        id: prefix
        text: root.prefix
        color: on_surface_variant
        font_size: '16sp'
        size_hint: None, None
        size: (self.texture_size[0] + dp(16), dp(56)) if root.prefix else (0, 0)
        pos: root.x, root.y
        halign: 'right'
    TextInput:
        id: ti
        multiline: root.multiline
        hint_text: root.hint
        size_hint: None, None
        size: root.width - prefix.width - dp(4), root.height - dp(10)
        pos: root.x + prefix.width + (0 if root.prefix else dp(4)), root.y + dp(1)
        padding: (0 if root.prefix else dp(12)), dp(16), dp(12), dp(16)
        font_size: '16sp'
        background_normal: ''
        background_active: ''
        background_color: 0, 0, 0, 0
        foreground_color: on_surface
        hint_text_color: on_surface_variant[:3] + [0.7]
        cursor_color: primary
        cursor_width: dp(2)
        on_focus: root.focused = self.focus
        selection_color: primary[:3] + [0.35]
    # floating label sitting in a notch on the top border
    Label:
        text: root.label
        color: primary if root.focused else on_surface_variant
        font_size: '12sp'
        size_hint: None, None
        size: self.texture_size[0] + dp(8), dp(16)
        pos: root.x + dp(12), root.top - dp(16)
        canvas.before:
            Color:
                rgba: root.bg
            Rectangle:
                pos: self.x, self.y + dp(4)
                size: self.width, dp(8)

<M3Switch>:
    thumb: dp(28) if self.state == 'down' else dp(16) + dp(8) * self.knob
    size_hint: None, None
    size: dp(52), dp(32)
    canvas:
        Color:
            rgba: primary if self.active else surface_highest
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]
        Color:
            rgba: [0, 0, 0, 0] if self.active else outline
        Line:
            rounded_rectangle: self.x + dp(1), self.y + dp(1), self.width - dp(2), self.height - dp(2), dp(15)
            width: dp(1)
        Color:
            rgba: on_primary if self.active else outline
        Ellipse:
            # thumb grows 16 -> 24dp when on, 28dp while pressed
            size: self.thumb, self.thumb
            pos: self.x + dp(16) + dp(20) * self.knob - self.thumb / 2, self.center_y - self.thumb / 2

<SwitchRow@ButtonBehavior+BoxLayout>:
    text: ''
    active: sw.active
    size_hint_y: None
    height: dp(52)
    spacing: dp(16)
    on_release: sw.active = not sw.active
    Label:
        text: root.text
        color: on_surface
        font_size: '16sp'
        text_size: self.size
        halign: 'left'
        valign: 'middle'
    M3Switch:
        id: sw
        active: root.active
        pos_hint: {'center_y': .5}

<Segment>:
    color: on_secondary_container if self.selected else on_surface
    font_size: '14sp'
    bold: self.selected
    canvas.before:
        Color:
            rgba: secondary_container if self.selected else [0, 0, 0, 0]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height / 2 if self.first else 0, self.height / 2 if self.last else 0, self.height / 2 if self.last else 0, self.height / 2 if self.first else 0]
        Color:
            rgba: on_surface[:3] + [0.12 if self.state == 'down' else 0]
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: [0, 0, 0, 0] if self.first else outline
        Line:
            points: self.x, self.y, self.x, self.top
            width: dp(1)
        # check mark before the label of the selected segment
        Color:
            rgba: on_secondary_container if self.selected else [0, 0, 0, 0]
        Line:
            points: [self.center_x - self.texture_size[0] / 2 - dp(18), self.center_y, self.center_x - self.texture_size[0] / 2 - dp(14), self.center_y - dp(4), self.center_x - self.texture_size[0] / 2 - dp(6), self.center_y + dp(4)]
            width: dp(1.4)

<SegmentedButton>:
    size_hint_y: None
    height: dp(40)
    canvas.after:
        Color:
            rgba: outline
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, self.height / 2 - dp(1)
            width: dp(1)

<LinearProgress>:
    size_hint_y: None
    height: dp(4)
    canvas:
        Color:
            rgba: secondary_container
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(2)]
        Color:
            rgba: primary
        RoundedRectangle:
            pos: self.pos
            size: self.width * self.value, self.height
            radius: [dp(2)]

<OptionsHeader>:
    size_hint_y: None
    height: dp(56)
    padding: dp(4), 0, dp(8), 0
    spacing: dp(16)
    canvas.before:
        Color:
            rgba: on_surface[:3] + [0.08 if self.state == 'down' else 0]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
    BoxLayout:
        orientation: 'vertical'
        padding: 0, dp(8)
        Label:
            text: 'Options'
            color: on_surface
            font_size: '16sp'
            text_size: self.size
            halign: 'left'
            valign: 'middle'
        Label:
            text: root.summary
            color: on_surface_variant
            font_size: '14sp'
            text_size: self.size
            halign: 'left'
            valign: 'middle'
            shorten: True
    Widget:
        size_hint: None, None
        size: dp(24), dp(24)
        pos_hint: {'center_y': .5}
        canvas:
            Color:
                rgba: on_surface_variant
            Line:
                # chevron: down when closed, up when open
                points: self.center_x - dp(6), self.center_y + dp(3) * (1 - 2 * root.open), self.center_x, self.center_y - dp(3) * (1 - 2 * root.open), self.center_x + dp(6), self.center_y + dp(3) * (1 - 2 * root.open)
                width: dp(1.5)
                cap: 'round'
                joint: 'round'

# -- track list ----------------------------------------------------------------

<TrackRow@ButtonBehavior+BoxLayout>:
    title: ''
    status: ''
    kind: 'queued'
    scolor: on_surface_variant
    size_hint_y: None
    height: dp(64)
    padding: dp(16), 0
    spacing: dp(16)
    on_release: app.show_details(self.title, self.status)
    canvas.before:
        Color:
            rgba: on_surface[:3] + [0.10 if self.state == 'down' else 0]
        Rectangle:
            pos: self.pos
            size: self.size
    Widget:
        size_hint: None, None
        size: dp(24), dp(24)
        pos_hint: {'center_y': .5}
        canvas:
            Color:
                rgba: outline[:3] + [1 if root.kind in ('queued', 'skipped') else 0]
            Line:
                circle: self.center_x, self.center_y, dp(10)
                width: dp(1.3)
            Color:
                rgba: outline[:3] + [1 if root.kind == 'skipped' else 0]
            Line:
                points: self.center_x - dp(4), self.center_y, self.center_x + dp(4), self.center_y
                width: dp(1.3)
            Color:
                rgba: primary[:3] + [1 if root.kind == 'active' else 0]
            Line:
                circle: self.center_x, self.center_y, dp(10), app.spin, app.spin + 270
                width: dp(2)
                cap: 'round'
            Color:
                rgba: success[:3] + [1 if root.kind == 'done' else 0]
            Ellipse:
                pos: self.x + dp(1), self.y + dp(1)
                size: dp(22), dp(22)
            Color:
                rgba: on_success[:3] + [1 if root.kind == 'done' else 0]
            Line:
                points: self.center_x - dp(5), self.center_y, self.center_x - dp(1.5), self.center_y - dp(3.5), self.center_x + dp(5), self.center_y + dp(3.5)
                width: dp(1.5)
            Color:
                rgba: error[:3] + [1 if root.kind == 'error' else 0]
            Ellipse:
                pos: self.x + dp(1), self.y + dp(1)
                size: dp(22), dp(22)
            Color:
                rgba: on_error[:3] + [1 if root.kind == 'error' else 0]
            Line:
                points: self.center_x, self.center_y - dp(1), self.center_x, self.center_y + dp(5.5)
                width: dp(1.5)
            Ellipse:
                pos: self.center_x - dp(1.4), self.center_y - dp(5.5)
                size: dp(2.8), dp(2.8)
    BoxLayout:
        orientation: 'vertical'
        padding: 0, dp(10)
        Label:
            text: root.title
            color: on_surface
            font_size: '16sp'
            text_size: self.width, None
            shorten: True
            shorten_from: 'right'
            halign: 'left'
        Label:
            text: root.status or 'Waiting'
            color: root.scolor
            font_size: '14sp'
            text_size: self.width, None
            shorten: True
            shorten_from: 'right'
            halign: 'left'

<LibRow@ButtonBehavior+BoxLayout>:
    name: ''
    info: ''
    path: ''
    folder: False
    size_hint_y: None
    height: dp(64)
    padding: dp(16), 0
    spacing: dp(16)
    on_release: app.open_entry(self.path, self.folder)
    canvas.before:
        Color:
            rgba: on_surface[:3] + [0.10 if self.state == 'down' else 0]
        Rectangle:
            pos: self.pos
            size: self.size
    Icon:
        text: ICONS['folder'] if root.folder else ICONS['music_note']
        color: on_secondary_container
        size_hint: None, None
        size: dp(40), dp(40)
        pos_hint: {'center_y': .5}
        canvas.before:
            Color:
                rgba: secondary_container
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(12) if root.folder else dp(20)]
    BoxLayout:
        orientation: 'vertical'
        padding: 0, dp(10)
        Label:
            text: root.name
            color: on_surface
            font_size: '16sp'
            text_size: self.width, None
            shorten: True
            shorten_from: 'right'
            halign: 'left'
        Label:
            text: root.info
            color: on_surface_variant
            font_size: '14sp'
            text_size: self.width, None
            shorten: True
            halign: 'left'

<NavItem>:
    orientation: 'vertical'
    padding: 0, dp(12), 0, dp(14)
    spacing: dp(4)
    AnchorLayout:
        Icon:
            text: root.icon
            color: on_secondary_container if root.active else on_surface_variant
            size_hint: None, None
            size: dp(64), dp(32)
            canvas.before:
                Color:
                    rgba: secondary_container if root.active else (on_surface[:3] + [0.08 if root.state == 'down' else 0])
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(16)]
    Label:
        text: root.text
        color: on_surface if root.active else on_surface_variant
        bold: root.active
        font_size: '12sp'
        size_hint_y: None
        height: dp(16)

<DetailsDialog>:
    size_hint: None, None
    width: min(Window.width - dp(48), dp(560))
    height: box.minimum_height
    background_color: 0, 0, 0, 0
    overlay_color: 0, 0, 0, 0.5
    BoxLayout:
        id: box
        orientation: 'vertical'
        padding: dp(24), dp(24), dp(16), dp(16)
        spacing: dp(16)
        canvas.before:
            Color:
                rgba: surface_high
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(28)]
        Label:
            text: root.title
            color: on_surface
            font_size: '22sp'
            size_hint_y: None
            height: self.texture_size[1]
            text_size: self.width - dp(8), None
            halign: 'left'
        ScrollView:
            size_hint_y: None
            height: min(body.height, Window.height * 0.5)
            Label:
                id: body
                text: root.body
                color: on_surface_variant
                font_size: '14sp'
                size_hint_y: None
                height: self.texture_size[1]
                text_size: self.width - dp(8), None
                halign: 'left'
        AnchorLayout:
            anchor_x: 'right'
            size_hint_y: None
            height: dp(40)
            TextButton:
                text: 'Close'
                size_hint_x: None
                width: dp(88)
                on_release: root.dismiss()

# -- screen --------------------------------------------------------------------

BoxLayout:
    orientation: 'vertical'
    # top grows by the status bar inset (edge-to-edge); the nav bar handles the bottom
    padding: 0, app.inset_top, 0, 0
    canvas.before:
        Color:
            rgba: surface
        Rectangle:
            pos: self.pos
            size: self.size

    # RelativeLayout: screens are positioned at (0, 0) of their parent
    RelativeLayout:
        ScreenManager:
            id: sm
            transition: FadeTransition(duration=0.15)
            on_current: app.on_tab(self.current)

            Screen:
                name: 'download'
                BoxLayout:
                    orientation: 'vertical'
                    # top app bar
                    BoxLayout:
                        size_hint_y: None
                        height: dp(64)
                        padding: dp(16), 0
                        spacing: dp(12)
                        Image:
                            source: ICON_PNG
                            size_hint: None, None
                            size: dp(32), dp(32)
                            pos_hint: {'center_y': .5}
                            mipmap: True
                        Label:
                            text: 'YT to MP3'
                            color: on_surface
                            font_size: '22sp'
                            text_size: self.size
                            halign: 'left'
                            valign: 'middle'

                    BoxLayout:
                        orientation: 'vertical'
                        padding: dp(16), 0, dp(16), dp(16)
                        spacing: dp(12)

                        OutlinedField:
                            id: urls
                            label: 'YouTube links'
                            hint: 'Video or playlist links, one per line'
                            multiline: True
                            height: dp(112)
                            bg: surface

                        BoxLayout:
                            size_hint_y: None
                            height: dp(32)
                            spacing: dp(8)
                            Chip:
                                icon: ICONS['content_paste']
                                text: 'Paste'
                                on_release: app.paste()
                            Chip:
                                icon: ICONS['close']
                                text: 'Clear'
                                on_release: urls.field.text = ''
                            Widget:

                        # collapsible options; the header shows a one-line summary
                        BoxLayout:
                            orientation: 'vertical'
                            size_hint_y: None
                            height: self.minimum_height
                            OptionsHeader:
                                summary: app.summary
                                open: app.opts_t
                                on_release: app.toggle_options()
                            ClipBox:
                                orientation: 'vertical'
                                spacing: dp(12)
                                padding: 0, dp(4), 0, dp(4)
                                size_hint_y: None
                                height: self.minimum_height * app.opts_t
                                opacity: app.opts_t
                                OutlinedField:
                                    id: folder
                                    label: 'Save to'
                                    prefix: 'Music /'
                                    bg: surface
                                BoxLayout:
                                    orientation: 'vertical'
                                    size_hint_y: None
                                    height: dp(64)
                                    spacing: dp(6)
                                    Label:
                                        text: 'Quality (kbps)'
                                        color: on_surface_variant
                                        font_size: '12sp'
                                        size_hint_y: None
                                        height: dp(18)
                                        padding: dp(4), 0
                                        text_size: self.size
                                        halign: 'left'
                                        valign: 'middle'
                                    SegmentedButton:
                                        id: bitrate
                                        values: app.bitrates
                                BoxLayout:
                                    orientation: 'vertical'
                                    size_hint_y: None
                                    height: dp(104)
                                    padding: dp(4), 0, 0, 0
                                    SwitchRow:
                                        id: subfolder
                                        text: 'Playlists into their own folder'
                                    SwitchRow:
                                        id: skip
                                        text: 'Skip existing files'

                        FilledButton:
                            id: start
                            text: ('Cancelling...' if app.cancelling else 'Cancel') if app.busy else 'Download MP3'
                            disabled: app.cancelling
                            bg: [0, 0, 0, 0] if app.busy else primary
                            fg: error if app.busy else on_primary
                            line: outline if app.busy else [0, 0, 0, 0]
                            height: dp(52)
                            on_release: app.cancel() if app.busy else app.start()

                        BoxLayout:
                            orientation: 'vertical'
                            size_hint_y: None
                            height: dp(32)
                            spacing: dp(8)
                            LinearProgress:
                                id: progress
                            Label:
                                id: status
                                text: 'Ready.'
                                color: on_surface_variant
                                font_size: '14sp'
                                text_size: self.size
                                halign: 'left'
                                valign: 'middle'
                                shorten: True
                                shorten_from: 'right'

                        # track list card
                        RelativeLayout:
                            canvas.before:
                                Color:
                                    rgba: surface_container
                                RoundedRectangle:
                                    pos: 0, 0
                                    size: self.size
                                    radius: [dp(16)]
                            Label:
                                text: 'Downloaded tracks show up here.\\nTip: share a video from the YouTube app.'
                                color: on_surface_variant[:3] + [0 if tracks.data else 0.8]
                                font_size: '14sp'
                                halign: 'center'
                            RecycleView:
                                id: tracks
                                # inset so rows never run under the rounded corners
                                size_hint_y: None
                                height: self.parent.height - dp(16)
                                y: dp(8)
                                viewclass: 'TrackRow'
                                bar_color: outline
                                bar_inactive_color: outline_variant
                                RecycleBoxLayout:
                                    default_size: None, dp(64)
                                    default_size_hint: 1, None
                                    size_hint_y: None
                                    height: self.minimum_height
                                    orientation: 'vertical'

            Screen:
                name: 'library'
                BoxLayout:
                    orientation: 'vertical'
                    # top app bar: back arrow inside subfolders
                    BoxLayout:
                        size_hint_y: None
                        height: dp(64)
                        padding: (dp(4) if app.lib_sub else dp(16)), 0, dp(4), 0
                        spacing: dp(4)
                        IconButton:
                            text: ICONS['arrow_back']
                            color: on_surface
                            pos_hint: {'center_y': .5}
                            opacity: 1 if app.lib_sub else 0
                            disabled: not app.lib_sub
                            width: dp(48) if app.lib_sub else 0
                            on_release: app.lib_up()
                        BoxLayout:
                            orientation: 'vertical'
                            padding: 0, dp(8)
                            Label:
                                text: app.lib_title
                                color: on_surface
                                font_size: '22sp'
                                text_size: self.size
                                halign: 'left'
                                valign: 'middle'
                                shorten: True
                            Label:
                                text: app.lib_where
                                color: on_surface_variant
                                font_size: '12sp'
                                size_hint_y: None
                                height: dp(16)
                                text_size: self.size
                                halign: 'left'
                                valign: 'middle'
                                shorten: True
                                shorten_from: 'left'
                        IconButton:
                            text: ICONS['refresh']
                            pos_hint: {'center_y': .5}
                            on_release: app.lib_refresh()
                    RelativeLayout:
                        size_hint: 1, 1
                        padding: 0
                        Label:
                            text: 'No MP3s here yet.\\nDownloads will show up in this list.'
                            color: on_surface_variant[:3] + [0 if lib.data else 0.8]
                            font_size: '14sp'
                            halign: 'center'
                        RecycleView:
                            id: lib
                            viewclass: 'LibRow'
                            bar_color: outline
                            bar_inactive_color: outline_variant
                            RecycleBoxLayout:
                                default_size: None, dp(64)
                                default_size_hint: 1, None
                                size_hint_y: None
                                height: self.minimum_height
                                padding: 0, 0, 0, dp(8)
                                orientation: 'vertical'

    # navigation bar (extends under the gesture/navigation bar)
    BoxLayout:
        size_hint_y: None
        height: dp(80) + app.inset_bottom
        padding: 0, 0, 0, app.inset_bottom
        canvas.before:
            Color:
                rgba: surface_container
            Rectangle:
                pos: self.pos
                size: self.size
        NavItem:
            icon: ICONS['file_download']
            text: 'Download'
            active: sm.current == 'download'
            on_release: sm.current = 'download'
        NavItem:
            icon: ICONS['library_music']
            text: 'Library'
            active: sm.current == 'library'
            on_release: sm.current = 'library'
"""


class FilledButton(ButtonBehavior, Label):
    """Pill button; Outlined/TextButton in kv only change the colors."""
    bg = ListProperty(C["primary"])
    fg = ListProperty(C["on_primary"])
    line = ListProperty([0, 0, 0, 0])


class LinearProgress(Widget):
    value = NumericProperty(0)  # 0..1


class OptionsHeader(ButtonBehavior, BoxLayout):
    summary = StringProperty("")
    open = NumericProperty(0)  # 0 closed .. 1 open (animated)


class NavItem(ButtonBehavior, BoxLayout):
    icon = StringProperty("")
    text = StringProperty("")
    active = BooleanProperty(False)


class ClipBox(BoxLayout, StencilView):
    """Clips its children (collapsible section) and ignores touches outside itself."""

    def on_touch_down(self, touch):
        return self.collide_point(*touch.pos) and super().on_touch_down(touch)


class OutlinedField(FloatLayout):
    """Material 3 outlined text field; the TextInput is `.field`."""
    label = StringProperty("")
    hint = StringProperty("")
    prefix = StringProperty("")
    multiline = BooleanProperty(False)
    focused = BooleanProperty(False)
    bg = ListProperty(C["surface"])  # behind the floating label
    field = ObjectProperty(None)


class M3Switch(ButtonBehavior, Widget):
    active = BooleanProperty(False)
    knob = NumericProperty(0)  # animated 0 (off) .. 1 (on)
    thumb = NumericProperty(0)  # diameter, set in kv

    def on_release(self):
        self.active = not self.active

    def on_active(self, *args):
        Animation.cancel_all(self, "knob")
        Animation(knob=float(self.active), d=0.15, t="out_quad").start(self)


class Segment(ButtonBehavior, Label):
    selected = BooleanProperty(False)
    first = BooleanProperty(False)
    last = BooleanProperty(False)


class SegmentedButton(BoxLayout):
    """Single-select Material 3 segmented button; `text` is the selected value."""
    values = ListProperty()
    text = StringProperty("")

    def on_values(self, *args):
        self.clear_widgets()
        n = len(self.values)
        for i, v in enumerate(self.values):
            seg = Segment(text=v, first=i == 0, last=i == n - 1, selected=v == self.text)
            seg.bind(on_release=lambda s: setattr(self, "text", s.text))
            self.add_widget(seg)

    def on_text(self, *args):
        for seg in self.children:
            seg.selected = seg.text == self.text


class DetailsDialog(ModalView):
    title = StringProperty("")
    body = StringProperty("")


def list_library(folder: Path):
    """LibRow data for one folder: subfolders (by name), then MP3s (newest first)."""
    dirs, files = [], []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    for e in entries:
        try:
            if e.is_dir():
                n = sum(1 for f in os.scandir(e.path) if f.name.lower().endswith(".mp3"))
                dirs.append({"name": e.name, "info": f"{n} track{'s' if n != 1 else ''}",
                             "path": e.path, "folder": True})
            elif e.name.lower().endswith(".mp3"):
                st = e.stat()
                files.append((st.st_mtime, {
                    "name": e.name[:-4], "path": e.path, "folder": False,
                    "info": f"{st.st_size / 1e6:.1f} MB  ·  {time.strftime('%d %b %Y', time.localtime(st.st_mtime))}"}))
        except OSError:
            continue
    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f[0], reverse=True)
    return dirs + [f for _, f in files]


def row_kind(text):
    if text.startswith("Error"):
        return "error"
    if text == "Done":
        return "done"
    if text.startswith(("Skipped", "Cancelled")):
        return "skipped"
    if text.startswith(("Downloading", "Converting")):
        return "active"
    return "queued"


class AndroidBridge:
    """Thin pyjnius wrapper; only used on Android, always from the Kivy (UI) thread."""

    def __init__(self, app):
        from android import activity, mActivity
        from jnius import autoclass

        self.activity = mActivity
        self._listeners = []
        self.Intent = autoclass("android.content.Intent")
        self.Scanner = autoclass("android.media.MediaScannerConnection")
        Environment = autoclass("android.os.Environment")
        self.sdk = autoclass("android.os.Build$VERSION").SDK_INT
        self.music_dir = Path(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC).getAbsolutePath())

        # temp files in the app cache; CA bundle for HTTPS
        cache = mActivity.getCacheDir().getAbsolutePath()
        os.environ["TMPDIR"] = cache
        tempfile.tempdir = cache
        try:
            import certifi
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        except ImportError:
            pass

        self._request_permissions()
        activity.bind(on_new_intent=lambda intent: Clock.schedule_once(lambda dt: self.handle_intent(app, intent)))
        self.handle_intent(app, mActivity.getIntent())

    def _request_permissions(self):
        from android.permissions import request_permissions

        if self.sdk >= 33:
            perms = ["android.permission.READ_MEDIA_AUDIO"]
        elif self.sdk >= 29:
            perms = ["android.permission.READ_EXTERNAL_STORAGE"]
        else:
            perms = ["android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE"]
        request_permissions(perms)

    def handle_intent(self, app, intent):
        """Links shared from the YouTube app (Share -> YT to MP3)."""
        if intent is None or intent.getAction() != self.Intent.ACTION_SEND:
            return
        text = intent.getStringExtra(self.Intent.EXTRA_TEXT) or ""
        intent.setAction(self.Intent.ACTION_MAIN)  # handle once
        app.add_urls(URL_RE.findall(text))

    def system_bar_insets(self):
        """(top, bottom) pixels covered by status/navigation bars.

        Apps targeting API 35 are drawn edge-to-edge on Android 15+, i.e. under the bars.
        Older Android versions lay the app out between the bars, so no padding is needed.
        """
        if self.sdk < 35:
            return 0, 0
        try:
            from jnius import autoclass

            insets = self.activity.getWindow().getDecorView().getRootWindowInsets()
            if insets is None:
                return 0, 0
            Type = autoclass("android.view.WindowInsets$Type")
            i = insets.getInsets(Type.systemBars() | Type.displayCutout())
            return i.top, i.bottom
        except Exception:
            return 0, 0

    def set_bar_colors(self, hex_color):
        """Status/navigation bars in the app background color (Android < 15; 15+ draws edge-to-edge)."""
        if self.sdk >= 35:
            return
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        color = autoclass("android.graphics.Color").parseColor(hex_color)

        @run_on_ui_thread
        def apply():
            window = self.activity.getWindow()
            window.setStatusBarColor(color)
            window.setNavigationBarColor(color)

        apply()

    def scan(self, path):
        """Make a new file visible to music players immediately."""
        self.Scanner.scanFile(self.activity, [str(path)], None, None)

    def open_audio(self, path, on_error):
        """Open an MP3 in the default music app.

        Other apps can't read file:// URIs, so the file is (re)scanned first and the
        content:// URI from MediaStore is passed to an ACTION_VIEW intent.
        """
        from android.runnable import run_on_ui_thread
        from jnius import JavaException, PythonJavaClass, java_method

        bridge = self

        @run_on_ui_thread
        def view(uri):
            intent = bridge.Intent(bridge.Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "audio/mpeg")
            intent.addFlags(bridge.Intent.FLAG_GRANT_READ_URI_PERMISSION)
            try:
                bridge.activity.startActivity(intent)
            except JavaException:
                Clock.schedule_once(lambda dt: on_error("No app found that can play MP3 files."))

        class Listener(PythonJavaClass):
            __javainterfaces__ = ["android/media/MediaScannerConnection$OnScanCompletedListener"]
            __javacontext__ = "app"

            @java_method("(Ljava/lang/String;Landroid/net/Uri;)V")
            def onScanCompleted(self, scanned, uri):
                bridge._listeners.remove(self)
                if uri is None:
                    Clock.schedule_once(lambda dt: on_error("Android could not index this file."))
                else:
                    view(uri)

        listener = Listener()
        self._listeners.append(listener)  # keep alive until the callback
        self.Scanner.scanFile(self.activity, [str(path)], ["audio/mpeg"], listener)

    def keep_screen_on(self, on):
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        flag = autoclass("android.view.WindowManager$LayoutParams").FLAG_KEEP_SCREEN_ON

        @run_on_ui_thread
        def apply():
            window = self.activity.getWindow()
            window.addFlags(flag) if on else window.clearFlags(flag)

        apply()

    def to_background(self):
        self.activity.moveTaskToBack(True)


class YtMp3App(App):
    bitrates = BITRATES
    inset_top = NumericProperty(0)
    inset_bottom = NumericProperty(0)
    busy = BooleanProperty(False)
    cancelling = BooleanProperty(False)
    spin = NumericProperty(0)  # angle of the "in progress" row indicator
    opts_t = NumericProperty(0)  # options section: 0 collapsed .. 1 expanded
    summary = StringProperty("")
    lib_title = StringProperty("Library")
    lib_where = StringProperty("")
    lib_sub = BooleanProperty(False)  # inside a playlist folder

    def build(self):
        self.title = "YT to MP3"
        Window.clearcolor = C["surface"]
        if not ANDROID:  # dev: phone-sized window
            Window.size = (400, 860)
        self.events = queue.Queue()
        self.worker = None
        self.rows = {}  # worker key -> index in RecycleView data
        self.root = Builder.load_string(KV)
        self.store = JsonStore(os.path.join(self.user_data_dir, "settings.json"))
        s = self.store.get("settings") if self.store.exists("settings") else {}
        ids = self.root.ids
        ids.folder.field.text = s.get("folder", "YT-MP3")
        ids.bitrate.text = s.get("bitrate", "192").split()[0]
        ids.subfolder.active = s.get("subfolder", True)
        ids.skip.active = s.get("skip", True)
        self.opts_t = 1.0 if s.get("options_open", False) else 0.0
        for w, prop in ((ids.folder.field, "text"), (ids.bitrate, "text"),
                        (ids.subfolder, "active"), (ids.skip, "active")):
            w.bind(**{prop: self._update_summary})
        self._update_summary()

        self.bridge = AndroidBridge(self) if ANDROID else None
        if self.bridge:
            self.bridge.set_bar_colors(M3["surface"])
        Window.softinput_mode = "below_target"  # keep the focused field above the keyboard
        Window.bind(on_keyboard=self._on_key, on_resize=lambda *a: Clock.schedule_once(self._apply_insets, 0.2))
        # insets are only known once the view is attached; re-check shortly after start
        for delay in (0, 0.5, 1.5):
            Clock.schedule_once(self._apply_insets, delay)
        Clock.schedule_interval(self._poll, 0.1)
        return self.root

    # -- helpers --------------------------------------------------------------

    @property
    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def music_dir(self) -> Path:
        return self.bridge.music_dir if self.bridge else Path.home() / "Music"

    def add_urls(self, urls):
        box = self.root.ids.urls.field
        existing = box.text.strip()
        new = [u for u in urls if u not in existing]
        if new:
            box.text = "\n".join(filter(None, [existing, *new]))

    def _apply_insets(self, *args):
        if self.bridge:
            self.inset_top, self.inset_bottom = self.bridge.system_bar_insets()

    def show_details(self, title, status):
        """Full title + status (errors are often too long for the row)."""
        if status:
            DetailsDialog(title=title, body=status).open()

    def _update_summary(self, *args):
        ids = self.root.ids
        parts = [f"Music/{ids.folder.field.text.strip() or 'YT-MP3'}", f"{ids.bitrate.text} kbps"]
        if not ids.skip.active:
            parts.append("overwrite")
        self.summary = "  ·  ".join(parts)

    def toggle_options(self):
        Animation.cancel_all(self, "opts_t")
        Animation(opts_t=0.0 if self.opts_t > 0.5 else 1.0, d=0.2, t="out_cubic").start(self)

    # -- library --------------------------------------------------------------

    def lib_root(self) -> Path:
        from yt_mp3.util import sanitize_filename
        return self.music_dir() / sanitize_filename(self.root.ids.folder.field.text.strip() or "YT-MP3", "YT-MP3")

    def on_tab(self, name):
        if name == "library":
            self.lib_path = self.lib_root()
            self.lib_refresh()

    def lib_refresh(self):
        root, path = self.lib_root(), getattr(self, "lib_path", None) or self.lib_root()
        if root not in (path, *path.parents):  # destination folder changed
            path = self.lib_path = root
        self.lib_sub = path != root
        self.lib_title = path.name if self.lib_sub else "Library"
        self.lib_where = str(path.relative_to(self.music_dir().parent)).replace(os.sep, "/")
        self.root.ids.lib.data = list_library(path)
        self.root.ids.lib.scroll_y = 1

    def lib_up(self):
        if self.lib_sub:
            self.lib_path = self.lib_path.parent
            self.lib_refresh()

    def open_entry(self, path, folder):
        if folder:
            self.lib_path = Path(path)
            self.lib_refresh()
        elif self.bridge:
            self.bridge.open_audio(path, lambda msg: DetailsDialog(title="Can't open file", body=msg).open())
        elif hasattr(os, "startfile"):  # dev on Windows
            os.startfile(path)

    def paste(self):
        self.add_urls(URL_RE.findall(Clipboard.paste() or ""))

    def _save_settings(self):
        ids = self.root.ids
        self.store.put("settings", folder=ids.folder.field.text.strip(), bitrate=ids.bitrate.text,
                       subfolder=ids.subfolder.active, skip=ids.skip.active, options_open=self.opts_t > 0.5)

    def _on_key(self, window, key, *args):
        if key != 27:
            return False
        sm = self.root.ids.sm
        if sm.current == "library":  # Back: up one folder, then to the Download tab
            if self.lib_sub:
                self.lib_up()
            else:
                sm.current = "download"
            return True
        if self.running and self.bridge:  # Back: keep downloading in the background
            self.bridge.to_background()
            return True
        return False

    # -- job ------------------------------------------------------------------

    def start(self):
        from yt_mp3.util import sanitize_filename
        from yt_mp3.worker import JobOptions, Worker

        ids = self.root.ids
        urls = [u.strip() for u in ids.urls.field.text.splitlines() if u.strip()]
        if not urls:
            ids.status.text = "Paste at least one YouTube link."
            return
        out = self.music_dir() / sanitize_filename(ids.folder.field.text.strip() or "YT-MP3", "YT-MP3")
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            ids.status.text = f"Cannot create {out}: {e}"
            return
        self._save_settings()

        ids.tracks.data = []
        self.rows.clear()
        ids.progress.value = 0
        self.worker = Worker(
            JobOptions(
                urls=urls,
                out_dir=out,
                bitrate_kbps=int(ids.bitrate.text),
                playlist_subfolder=ids.subfolder.active,
                skip_existing=ids.skip.active,
                on_saved=lambda p: self.events.put(("saved", p)),
            ),
            self.events,
        )
        self._set_busy(True)
        ids.status.text = "Starting..."
        self.worker.start()

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancelling = True
            self.root.ids.status.text = "Cancelling..."

    def _set_busy(self, busy):
        self.busy = busy
        self.cancelling = False
        if busy:
            self._spinner = Clock.schedule_interval(self._spin, 1 / 30)
        elif getattr(self, "_spinner", None):
            self._spinner.cancel()
        if self.bridge:
            self.bridge.keep_screen_on(busy)

    def _spin(self, dt):
        self.spin = (self.spin + 360 * dt) % 360

    def on_stop(self):
        if self.worker:
            self.worker.cancel.set()

    # -- worker events (UI thread) --------------------------------------------

    def _poll(self, dt):
        rv = self.root.ids.tracks
        changed = False
        try:
            for _ in range(500):
                changed |= self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        if changed:
            rv.refresh_from_data()

    def _handle(self, event):
        ids = self.root.ids
        kind = event[0]
        if kind == "add":
            _, key, title = event
            self.rows[key] = len(ids.tracks.data)
            ids.tracks.data.append({"title": title, "status": "", "kind": "queued",
                                    "scolor": C["on_surface_variant"]})
            return True
        if kind == "track":
            _, key, text = event
            idx = self.rows.get(key)
            if idx is None:
                return False
            row = ids.tracks.data[idx]
            row["kind"] = row_kind(text)
            row["status"], row["scolor"] = text, C[STATUS_COLOR[row["kind"]]]
            return True
        if kind == "overall":
            _, frac, text = event
            if frac is not None:
                ids.progress.value = frac
            if text:
                ids.status.text = text
        elif kind == "saved":
            if self.bridge:
                self.bridge.scan(event[1])
            if self.root.ids.sm.current == "library":
                self.lib_refresh()
        elif kind == "done":
            ids.status.text = event[1]
            self._set_busy(False)
        return False


if __name__ == "__main__":
    YtMp3App().run()
