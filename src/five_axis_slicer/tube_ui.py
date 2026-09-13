"""Qt page for the first Tube Setup and coordinate-system workflow."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import machine_profile_ui, tube_operation_ui
from . import tube_ui_presenter as presenter
from .command_kernel import CommandInvocation, CommandResult
from .manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
)
from .manufacturing.library import (
    UserResourceLibrary,
    default_user_resource_library_root,
)
from .manufacturing.machine import MachineProfile
from .manufacturing.own_printer import default_printer_setup
from .manufacturing.resources import (
    MaterialProfile,
    NozzleProfile,
    ResourceSnapshot,
)
from .manufacturing.setup import (
    BUILD_CS_NODE,
    MACHINE_NODE,
    MATERIAL_NODE,
    MODEL_CS_NODE,
    NOZZLE_NODE,
    OPERATION_NODE,
    PART_NODE,
    PLACEMENT_NODE,
    IssueSeverity,
    NodeState,
)
from .models import (
    CadModel,
    PickHit,
    PickRequest,
)
from .step_loader import geometry_candidates
from .tube_commands import TubeCommandProvider
from .tube_controller import BodyRole, DraftNotFoundError, TubeSetupController
from .tube_drafts import CoordinateFrameDraft
from .tube_resource_selection import NozzleEditorError
from .tube_ui_text import (
    TUBE_CONTROL_TEXT,
    apply_tube_help,
    setup_tree_node,
    tube_language,
)
from .tube_ui_text import (
    TUBE_TEXT as _TEXT,
)
from .ui_controls import OptionalDoubleSpinBox
from .viewer import ModelViewer

_NODE_ORDER = (
    PART_NODE,
    MACHINE_NODE,
    NOZZLE_NODE,
    MATERIAL_NODE,
    MODEL_CS_NODE,
    BUILD_CS_NODE,
    PLACEMENT_NODE,
)
_COORDINATE_DEFAULTS = {
    "origin": (0.0, 0.0, 0.0),
    "z": (0.0, 0.0, 1.0),
    "x": (1.0, 0.0, 0.0),
}
_RESOURCE_KINDS = frozenset(("machine", "nozzle", "material"))
CommandExecutor = Callable[[CommandInvocation], CommandResult]
_DIRECT_COMMANDS = TubeCommandProvider()


def _make_spin(low: float, high: float, value: float, decimals: int) -> QDoubleSpinBox:
    spin = OptionalDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setValue(value)
    spin.setKeyboardTracking(False)
    return spin


def _set_compact_tree_actions(*buttons: QPushButton) -> None:
    for button in buttons:
        button.setStyleSheet("min-height: 14px; padding: 4px 10px;")
        button.setFixedHeight(30)


class TubeSetupPage(QWidget):
    back_requested = pyqtSignal()
    open_step_requested = pyqtSignal()
    update_source_requested = pyqtSignal()
    save_requested = pyqtSignal()
    state_changed = pyqtSignal(dict)
    error_raised = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        viewer_factory: Callable[[QWidget], QWidget] | None = None,
        resource_library: UserResourceLibrary | None = None,
    ) -> None:
        super().__init__(parent)
        self.language = "zh"
        self.model: CadModel | None = None
        self.resource_library = resource_library or UserResourceLibrary(
            default_user_resource_library_root()
        )
        self.controller = TubeSetupController(
            setup=default_printer_setup(), resource_library=self.resource_library
        )
        self._command_executor: CommandExecutor | None = None
        factory = viewer_factory or ModelViewer
        self.viewer = factory(self)
        self.viewer.setMinimumHeight(280)
        if hasattr(self.viewer, "set_pick_callback"):
            self.viewer.set_pick_callback(self._on_pick_hit)
        self._view_mode = "model"
        self._tree_items: dict[str, QTreeWidgetItem] = {}
        self._role_combos: dict[str, QComboBox] = {}
        self._candidate_payloads: dict[str, list[dict[str, Any]]] = {
            "origins": [],
            "directions": [],
        }
        self._coordinate_node = MODEL_CS_NODE
        self._selected_operation_id: str | None = None
        self._selected_operation_type = "tube_thin_wall_indexed"
        self._coordinate_control_dirty: set[str] = set()
        self._updating_coordinate_controls = False
        self._updating_placement_controls = False
        self._pick_context: tuple[str, str, str] | None = None
        self._two_point_hits: list[PickHit] = []
        self._machine_profiles: dict[str, MachineProfile] = {}
        self._nozzle_profiles: dict[str, NozzleProfile] = {}
        self._material_profiles: dict[str, MaterialProfile] = {}
        self._resource_origins: dict[str, dict[str, str]] = {}
        self._reload_resource_catalogs(populate_widgets=False)
        self._build_ui()
        self.set_language("zh")
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._build_tree_panel())
        body.addWidget(self._build_viewer_panel(), 1)
        body.addWidget(self._build_editor_panel())
        root.addLayout(body, 1)

        issue_panel = QFrame()
        issue_panel.setObjectName("glassPanel")
        issue_layout = QVBoxLayout(issue_panel)
        issue_layout.setContentsMargins(10, 8, 10, 8)
        self.issue_title = QLabel()
        self.issue_title.setObjectName("panelTitle")
        self.issue_list = QListWidget()
        self.issue_list.setObjectName("tubeIssueList")
        self.issue_list.setMaximumHeight(45)
        self.issue_list.itemActivated.connect(self._jump_to_issue)
        issue_layout.addWidget(self.issue_title)
        issue_layout.addWidget(self.issue_list)
        root.addWidget(issue_panel)

    def _build_tree_panel(self) -> QWidget:
        panel = QFrame()
        self.tree_panel = panel
        panel.setObjectName("glassPanel")
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)
        self.title_label = QLabel()
        self.title_label.setObjectName("panelTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("mutedText")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)

        buttons = QGridLayout()
        buttons.setVerticalSpacing(6)
        self.back_button, self.open_button = QPushButton(), QPushButton()
        self.update_source_button = QPushButton()
        self.save_button = QPushButton()
        self.create_operation_button = QPushButton()
        self.operation_type_combo = QComboBox()
        self.update_source_button.setMinimumWidth(180)
        self.create_operation_button.setObjectName("primaryButton")
        _set_compact_tree_actions(
            self.back_button,
            self.open_button,
            self.update_source_button,
            self.save_button,
            self.create_operation_button,
        )
        self.back_button.clicked.connect(self.back_requested)
        self.open_button.clicked.connect(self.open_step_requested)
        self.update_source_button.clicked.connect(self.update_source_requested)
        self.save_button.clicked.connect(self.save_requested)
        self.create_operation_button.clicked.connect(self._create_operation)
        buttons.addWidget(self.back_button, 0, 0)
        buttons.addWidget(self.open_button, 0, 1)
        buttons.addWidget(self.update_source_button, 1, 0, 1, 2)
        buttons.addWidget(self.save_button, 2, 0, 1, 2)
        for operation_type in self.controller.available_operation_types:
            self.operation_type_combo.addItem(
                self._t(f"operation_type_{operation_type}"), operation_type
            )
        buttons.addWidget(self.operation_type_combo, 3, 0, 1, 2)
        buttons.addWidget(self.create_operation_button, 4, 0, 1, 2)
        layout.addLayout(buttons)

        self.tree = QTreeWidget()
        self.tree.setObjectName("tubeOperationTree")
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self.activate_selected_editor)
        layout.addWidget(self.tree, 1)
        self.coordinate_status = QLabel()
        self.coordinate_status.setObjectName("valueText")
        self.setup_status = QLabel()
        self.setup_status.setObjectName("valueText")
        layout.addWidget(self.coordinate_status)
        layout.addWidget(self.setup_status)
        return panel

    def _build_viewer_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QFrame()
        toolbar.setObjectName("progressPanel")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        self.model_view_button, self.machine_view_button = QPushButton(), QPushButton()
        self.model_view_button.setMinimumWidth(128)
        self.machine_view_button.setMinimumWidth(128)
        self.model_view_button.clicked.connect(lambda: self.set_view_mode("model"))
        self.machine_view_button.clicked.connect(lambda: self.set_view_mode("machine"))
        toolbar_layout.addWidget(self.model_view_button)
        toolbar_layout.addWidget(self.machine_view_button)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)
        layout.addWidget(self.viewer, 1)
        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QFrame()
        self.editor_panel = panel
        panel.setObjectName("glassPanel")
        panel.setFixedWidth(460)
        layout = QVBoxLayout(panel)
        self.editor_title = QLabel()
        self.editor_title.setObjectName("panelTitle")
        self.editor_stack = QStackedWidget()
        self.empty_editor = QLabel()
        self.empty_editor.setWordWrap(True)
        self.part_editor = self._build_part_editor()
        self.machine_editor = self._build_machine_editor()
        self.nozzle_editor = self._build_nozzle_editor()
        self.material_editor = self._build_material_editor()
        self.coordinate_editor = self._build_coordinate_editor()
        self.placement_editor = self._build_placement_editor()
        self.operation_editor = tube_operation_ui.build_editor(self)
        for editor in (
            self.empty_editor,
            self.part_editor,
            self.machine_editor,
            self.nozzle_editor,
            self.material_editor,
            self.coordinate_editor,
            self.placement_editor,
            self.operation_editor,
        ):
            self.editor_stack.addWidget(editor)
        self.editor_scroll = QScrollArea()
        self.editor_scroll.setWidgetResizable(True)
        self.editor_scroll.setFrameShape(QFrame.NoFrame)
        self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.editor_scroll.setWidget(self.editor_stack)
        layout.addWidget(self.editor_title)
        layout.addWidget(self.editor_scroll, 1)
        _add_operation_footer(self, layout)
        return panel

    def _build_part_editor(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.part_help = _help_label()
        self.part_table = QTableWidget(0, 3)
        self.part_table.setObjectName("tubePartTable")
        self.part_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.part_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.part_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.part_confirm_button = QPushButton()
        self.part_confirm_button.setObjectName("primaryButton")
        self.part_confirm_button.clicked.connect(self._confirm_part)
        layout.addWidget(self.part_help)
        layout.addWidget(self.part_table, 1)
        layout.addWidget(self.part_confirm_button)
        return page

    def _build_machine_editor(self) -> QWidget:
        return machine_profile_ui.build_editor(self)

    def _build_nozzle_editor(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.nozzle_help = _help_label()
        self.nozzle_combo = QComboBox()
        for key, profile in self._nozzle_profiles.items():
            self.nozzle_combo.addItem(
                self._resource_choice_label("nozzle", key, profile),
                key,
            )
        form = QFormLayout()
        self.nozzle_interface = QLineEdit()
        self.nozzle_length = _make_spin(0.0, 1000.0, 0.0, 6)
        self.nozzle_collision = QCheckBox()
        self.nozzle_interface_label = QLabel()
        self.nozzle_length_label = QLabel()
        form.addRow(self.nozzle_interface_label, self.nozzle_interface)
        form.addRow(self.nozzle_length_label, self.nozzle_length)
        form.addRow(self.nozzle_collision)
        self.nozzle_apply_button = QPushButton()
        self.nozzle_apply_button.setObjectName("primaryButton")
        self.nozzle_apply_button.clicked.connect(self._apply_nozzle)
        self.nozzle_combo.currentIndexChanged.connect(lambda _index: _sync_nozzle_editor(self))
        layout.addWidget(self.nozzle_help)
        layout.addWidget(self.nozzle_combo)
        layout.addLayout(form)
        layout.addWidget(self.nozzle_apply_button)
        layout.addStretch(1)
        return page

    def _build_material_editor(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.material_help = _help_label()
        self.material_combo = QComboBox()
        for key, profile in self._material_profiles.items():
            self.material_combo.addItem(
                self._resource_choice_label("material", key, profile),
                key,
            )
        self.material_review = QCheckBox()
        self.material_detail = QLabel()
        self.material_detail.setWordWrap(True)
        self.material_apply_button = QPushButton()
        self.material_apply_button.setObjectName("primaryButton")
        self.material_apply_button.clicked.connect(self._apply_material)
        self.material_combo.currentIndexChanged.connect(lambda _index: _sync_material_editor(self))
        layout.addWidget(self.material_help)
        layout.addWidget(self.material_combo)
        layout.addWidget(self.material_detail)
        layout.addWidget(self.material_review)
        layout.addWidget(self.material_apply_button)
        layout.addStretch(1)
        return page

    def _build_coordinate_editor(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.coordinate_help = _help_label()
        self.coordinate_inputs: dict[
            str, tuple[QComboBox, tuple[QDoubleSpinBox, ...], QPushButton, QLabel]
        ] = {}
        for component, defaults in _COORDINATE_DEFAULTS.items():
            self._add_coordinate_group(layout, component, defaults)
        buttons = QHBoxLayout()
        self.coordinate_apply_button = QPushButton()
        self.coordinate_apply_button.setObjectName("primaryButton")
        self.coordinate_cancel_button = QPushButton()
        self.coordinate_apply_button.clicked.connect(self._apply_coordinate)
        self.coordinate_cancel_button.clicked.connect(self._cancel_coordinate)
        buttons.addWidget(self.coordinate_apply_button)
        buttons.addWidget(self.coordinate_cancel_button)
        self.coordinate_feedback = QLabel()
        self.coordinate_feedback.setWordWrap(True)
        layout.insertWidget(0, self.coordinate_help)
        layout.addLayout(buttons)
        layout.addWidget(self.coordinate_feedback)
        layout.addStretch(1)
        return page

    def _add_coordinate_group(
        self,
        layout: QVBoxLayout,
        component: str,
        defaults: tuple[float, float, float],
    ) -> None:
        group = QFrame()
        group.setObjectName("progressPanel")
        grid = QGridLayout(group)
        title = QLabel()
        title.setObjectName("valueText")
        combo = QComboBox()
        values = tuple(_make_spin(-1.0e6, 1.0e6, value, 6) for value in defaults)
        pick, confirm, flip = QPushButton(), QPushButton(), QPushButton()
        pick.clicked.connect(lambda _checked=False: self._start_pick(component))
        confirm.clicked.connect(
            lambda _checked=False: self._confirm_coordinate_component(component)
        )
        if component != "origin":
            flip.clicked.connect(lambda _checked=False: self._flip_coordinate(component))
        grid.addWidget(title, 0, 0, 1, 4)
        grid.addWidget(combo, 1, 0, 1, 4)
        for index, spin in enumerate(values):
            spin.setPrefix(f"{'XYZ'[index]} ")
            grid.addWidget(spin, 2, index)
        grid.addWidget(pick, 3, 0)
        grid.addWidget(confirm, 3, 1, 1, 2)
        if component != "origin":
            grid.addWidget(flip, 3, 3)
        layout.addWidget(group)
        self.coordinate_inputs[component] = (combo, values, pick, title)
        setattr(self, f"{component}_confirm_button", confirm)
        setattr(self, f"{component}_flip_button", flip)
        combo.currentIndexChanged.connect(
            lambda _index: self._coordinate_candidate_changed(component)
        )
        for spin in values:
            spin.valueChanged.connect(lambda _value: self._coordinate_value_changed(component))

    def _build_placement_editor(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.placement_help = _help_label()
        form = QFormLayout()
        self.mount_combo = QComboBox()
        self.mount_combo.currentIndexChanged.connect(self._placement_mount_changed)
        self.mount_label = QLabel()
        form.addRow(self.mount_label, self.mount_combo)
        self.placement_spins: dict[str, QDoubleSpinBox] = {}
        self.placement_labels: dict[str, QLabel] = {}
        for key in ("dx", "dy", "dz", "rx", "ry", "rz"):
            spin = _make_spin(-100000.0, 100000.0, 0.0, 4)
            if key.startswith("r"):
                spin.setRange(-360.0, 360.0)
                spin.setSuffix("°")
            else:
                spin.setSuffix(" mm")
            self.placement_spins[key] = spin
            self.placement_labels[key] = QLabel(key.upper())
            spin.valueChanged.connect(self._placement_adjustment_changed)
            form.addRow(self.placement_labels[key], spin)
        buttons = QHBoxLayout()
        self.placement_apply_button = QPushButton()
        self.placement_apply_button.setObjectName("primaryButton")
        self.placement_cancel_button = QPushButton()
        self.placement_apply_button.clicked.connect(self._apply_placement)
        self.placement_cancel_button.clicked.connect(self._cancel_placement)
        buttons.addWidget(self.placement_apply_button)
        buttons.addWidget(self.placement_cancel_button)
        self.placement_feedback = QLabel()
        self.placement_feedback.setWordWrap(True)
        layout.addWidget(self.placement_help)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.placement_feedback)
        layout.addStretch(1)
        return page

    def _reload_resource_catalogs(
        self,
        *,
        populate_widgets: bool = True,
        follow_setup: frozenset[str] = frozenset(),
    ) -> None:
        """Load selectable resources and retain divergent project snapshots."""

        catalogs: dict[str, dict[str, Any]] = {
            "machine": {},
            "nozzle": {},
            "material": {},
        }
        origins: dict[str, dict[str, str]] = {
            "machine": {},
            "nozzle": {},
            "material": {},
        }
        for kind in catalogs:
            builtin_ids = {
                _resource_profile_id(profile)
                for profile in self.resource_library.builtin_profiles(kind)
            }
            for profile in self.controller.available_resource_profiles(kind):
                key = _resource_profile_id(profile)
                catalogs[kind][key] = profile
                origins[kind][key] = "builtin" if key in builtin_ids else "user"

            snapshot = getattr(self.controller.setup, kind)
            if snapshot is None:
                continue
            matching_key = _matching_profile_key(kind, snapshot, catalogs[kind])
            if matching_key is not None:
                continue
            try:
                profile = _profile_from_snapshot(kind, snapshot)
            except (TypeError, ValueError):
                continue
            snapshot_key = f"project-snapshot:{kind}:{snapshot.content_hash}"
            catalogs[kind][snapshot_key] = profile
            audit = next(
                (item for item in self.controller.resource_audits if item.resource_type == kind),
                None,
            )
            status = "missing" if audit is None else audit.status
            origins[kind][snapshot_key] = f"snapshot:{status}"

        self._machine_profiles = dict(catalogs["machine"])
        self._nozzle_profiles = dict(catalogs["nozzle"])
        self._material_profiles = dict(catalogs["material"])
        self._resource_origins = origins
        if populate_widgets and hasattr(self, "machine_combo"):
            self._populate_resource_combos(follow_setup=follow_setup)

    def _populate_resource_combos(
        self,
        *,
        follow_setup: frozenset[str] = frozenset(),
    ) -> None:
        for kind, combo, profiles in (
            ("machine", self.machine_combo, self._machine_profiles),
            ("nozzle", self.nozzle_combo, self._nozzle_profiles),
            ("material", self.material_combo, self._material_profiles),
        ):
            previous_key = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for key, profile in profiles.items():
                combo.addItem(self._resource_choice_label(kind, key, profile), key)
            selected_key = self._selected_resource_key(kind, profiles)
            target_key = selected_key if kind in follow_setup else previous_key
            if target_key not in profiles:
                target_key = selected_key
            index = combo.findData(target_key)
            combo.setCurrentIndex(index if index >= 0 else (0 if combo.count() else -1))
            combo.blockSignals(False)
        self._update_machine_detail()
        self._update_material_detail()

    def _selected_resource_key(
        self,
        kind: str,
        profiles: Mapping[str, Any],
    ) -> str | None:
        snapshot = getattr(self.controller.setup, kind)
        if snapshot is None:
            return None
        return _matching_profile_key(kind, snapshot, profiles)

    def _resource_choice_label(self, kind: str, key: str, profile: Any) -> str:
        name = (
            machine_profile_ui.display_name(profile, self.language)
            if isinstance(profile, MachineProfile)
            else profile.display_name
        )
        origin = self._resource_origins.get(kind, {}).get(key, "user")
        if origin == "builtin":
            qualifier = self._t("resource_origin_builtin")
        elif origin == "user":
            qualifier = self._t("resource_origin_user")
        else:
            _prefix, _separator, status = origin.partition(":")
            status_key = (
                "resource_status_diverged" if status == "diverged" else "resource_status_missing"
            )
            qualifier = f"{self._t('resource_origin_snapshot')} · {self._t(status_key)}"
        return f"{name}  [{qualifier}]"

    def reload_resource_library(self) -> None:
        """Refresh profiles and audits after an external library change."""

        self.controller.refresh_resource_library()
        self._reload_resource_catalogs()
        _sync_nozzle_editor(self)
        _sync_material_editor(self)
        self.refresh()

    def set_language(self, language: str) -> None:
        self.language = tube_language(language)
        t = self._t
        for control, key in TUBE_CONTROL_TEXT:
            getattr(self, control).setText(t(key))
        for index in range(self.operation_type_combo.count()):
            operation_type = self.operation_type_combo.itemData(index)
            self.operation_type_combo.setItemText(index, t(f"operation_type_{operation_type}"))
        tube_operation_ui.retranslate(self, t)
        english = self.language == "en"
        self.tree_panel.setFixedWidth(380 if english else 340)
        self.editor_panel.setFixedWidth(580 if english else 460)
        view_width = 220 if english else 128
        self.model_view_button.setMinimumWidth(view_width)
        self.machine_view_button.setMinimumWidth(view_width)
        self.part_table.setHorizontalHeaderLabels((t("body"), t("kind"), t("role")))
        self.coordinate_help.setText(
            t(
                "coordinate_help_model"
                if self._coordinate_node == MODEL_CS_NODE
                else "coordinate_help_build"
            )
        )
        for component, label_key in (
            ("origin", "origin"),
            ("z", "z_direction"),
            ("x", "x_direction"),
        ):
            _combo, _values, pick, title = self.coordinate_inputs[component]
            title.setText(t(label_key))
            pick.setText(t("pick"))
            getattr(self, f"{component}_confirm_button").setText(t("confirm"))
            if component != "origin":
                getattr(self, f"{component}_flip_button").setText(t("flip"))
        self._populate_resource_combos()
        self._retranslate_part_roles()
        self._rebuild_tree()
        self._populate_coordinate_candidates(preserve_selection=True)
        self.refresh()

    def _t(self, key: str) -> str:
        return _TEXT[self.language][key]

    def set_model(self, model: CadModel) -> None:
        self.model = model
        self.controller.attach_cad_model(model)
        self._candidate_payloads = geometry_candidates(model)
        if hasattr(self.viewer, "load_model"):
            self.viewer.load_model(model)
        self._populate_part_table()
        self._populate_coordinate_candidates()
        self.set_view_mode("model")
        self.refresh()

    def set_controller(self, controller: TubeSetupController, model: CadModel | None) -> None:
        if not isinstance(controller, TubeSetupController):
            raise TypeError("controller must be TubeSetupController")
        self.controller = controller
        self.controller.set_resource_library(self.resource_library)
        self.model = model
        self._pick_context = None
        self._two_point_hits.clear()
        self._coordinate_control_dirty.clear()
        if model is not None:
            self.controller.attach_cad_model(model, mark_modified=False)
            self._candidate_payloads = geometry_candidates(model)
            if hasattr(self.viewer, "load_model"):
                self.viewer.load_model(model)
        else:
            self._candidate_payloads = {"origins": [], "directions": []}
            if hasattr(self.viewer, "clear_model"):
                self.viewer.clear_model()
            elif hasattr(self.viewer, "clear_selection"):
                self.viewer.clear_selection()
            if hasattr(self.viewer, "set_pick_request"):
                self.viewer.set_pick_request(PickRequest("body", multiple=True))
            self.set_view_mode("model")
        self._reload_resource_catalogs(follow_setup=_RESOURCE_KINDS)
        _sync_nozzle_editor(self)
        _sync_material_editor(self)
        self._populate_part_table()
        self._populate_coordinate_candidates()
        self.refresh()

    def set_command_executor(self, callback: CommandExecutor | None) -> None:
        """Route applied Setup changes through the application command boundary."""
        self._command_executor = callback

    def _execute_command(
        self, name: str, *args: Any, command_origin: str = "gui", **kwargs: Any
    ) -> Any:
        invocation = CommandInvocation(name, args, kwargs, origin=command_origin)
        if self._command_executor is not None:
            return self._command_executor(invocation).payload
        outcome = _DIRECT_COMMANDS.invoke(self.controller, invocation)  # type: ignore[arg-type]
        self.refresh()
        return outcome.payload

    def _rebuild_tree(self) -> None:
        selected = self.tree.currentItem().data(0, Qt.UserRole) if self.tree.currentItem() else None
        self.tree.blockSignals(True)
        self.tree.clear()
        self._tree_items.clear()
        project = QTreeWidgetItem((self._t("project"),))
        project.setData(0, Qt.UserRole, "project")
        model = QTreeWidgetItem((self._t("model"),))
        model.setData(0, Qt.UserRole, "model")
        setup = QTreeWidgetItem((self._t("setup"),))
        setup.setData(0, Qt.UserRole, "setup")
        operations = QTreeWidgetItem((self._t("operations"),))
        operations.setData(0, Qt.UserRole, "operations")
        self.tree.addTopLevelItem(project)
        project.addChild(model)
        project.addChild(setup)
        project.addChild(operations)
        self._tree_items["model"] = model
        for node in _NODE_ORDER:
            item = QTreeWidgetItem((self._t(node),))
            item.setData(0, Qt.UserRole, node)
            setup.addChild(item)
            self._tree_items[node] = item
        for operation in self.controller.operations:
            item = QTreeWidgetItem((operation.name,))
            operation_node = f"operation:{operation.operation_id}"
            item.setData(0, Qt.UserRole, operation_node)
            operations.addChild(item)
            self._tree_items[operation_node] = item
        self._tree_items[OPERATION_NODE] = operations
        project.setExpanded(True)
        setup.setExpanded(True)
        operations.setExpanded(True)
        selected = (
            selected
            if isinstance(selected, str)
            and selected.startswith("operation:")
            and selected in self._tree_items
            else setup_tree_node(selected, self._tree_items, self.controller.validation_report())
        )
        self.tree.setCurrentItem(self._tree_items[selected])
        self.tree.blockSignals(False)

    def refresh(self) -> None:
        self._rebuild_tree()
        report = self.controller.validation_report()
        for node, item in self._tree_items.items():
            if node not in report.node_states:
                continue
            state = report.node_states[node]
            base = self._t("operations") if node == OPERATION_NODE else self._t(node)
            item.setText(0, f"{base}  [{self._t('status_' + state.value)}]")
            item.setForeground(0, _state_color(state))
        self.create_operation_button.setEnabled(self.controller.can_create_operation)
        self.operation_type_combo.setEnabled(self.controller.can_create_operation)
        self.update_source_button.setEnabled(self.model is not None)
        self.coordinate_status.setText(
            f"{self._t('coordinates_valid')}: {'✓' if report.coordinates_valid else '—'}"
        )
        ready_label = self._t("setup_ready")
        if report.setup_ready and report.has_warnings:
            ready_value = self._t("ready_warning")
        else:
            ready_value = "✓" if report.setup_ready else "—"
        self.setup_status.setText(f"{ready_label}: {ready_value}")
        self.issue_list.clear()
        for issue in report.issues:
            marker = {
                IssueSeverity.ERROR: "E",
                IssueSeverity.WARNING: "W",
                IssueSeverity.INFO: "I",
            }[issue.severity]
            self.issue_list.addItem(
                f"[{marker}] {issue.code} · {issue.object_id or self.controller.setup.setup_id}"
            )
            self.issue_list.item(self.issue_list.count() - 1).setData(Qt.UserRole, issue.to_json())
        if not report.issues:
            self.issue_list.addItem(self._t("no_issues"))
        self._refresh_overlays()
        self.state_changed.emit(self.controller.state_json())

    def activate_selected_editor(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        node = item.data(0, Qt.UserRole)
        editors = {
            PART_NODE: self.part_editor,
            MACHINE_NODE: self.machine_editor,
            NOZZLE_NODE: self.nozzle_editor,
            MATERIAL_NODE: self.material_editor,
            MODEL_CS_NODE: self.coordinate_editor,
            BUILD_CS_NODE: self.coordinate_editor,
            PLACEMENT_NODE: self.placement_editor,
            "operation": self.operation_editor,
        }
        is_operation = isinstance(node, str) and node.startswith("operation:")
        editor = editors.get("operation" if is_operation else node, self.empty_editor)
        self.editor_stack.setCurrentWidget(editor)
        _set_operation_footer_visible(self, is_operation)
        self.editor_title.setText(
            self._t("operation")
            if is_operation
            else self._t(node)
            if node in _TEXT[self.language]
            else ""
        )
        if node == PART_NODE:
            self._populate_part_table()
            self.set_view_mode("model")
        elif node in {MODEL_CS_NODE, BUILD_CS_NODE}:
            self._begin_coordinate_editor(node)
            self.set_view_mode("model")
        elif node == PLACEMENT_NODE:
            self._begin_placement_editor()
            self.set_view_mode("machine")
        elif node == MACHINE_NODE:
            self._update_machine_detail()
        elif node == MATERIAL_NODE:
            self._update_material_detail()
        elif is_operation:
            tube_operation_ui.populate_editor(self, node.removeprefix("operation:"))

    def activate_coordinate_entry(self) -> None:
        self.refresh()
        self.activate_selected_editor()

    def _populate_part_table(self) -> None:
        roles = self.controller.body_roles()
        candidates = self.controller.body_candidates
        self.part_table.setRowCount(len(candidates))
        self._role_combos.clear()
        for row, body in enumerate(candidates):
            name_item = QTableWidgetItem(f"{body.body_id} · {body.name}")
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            kind_item = QTableWidgetItem(body.kind)
            kind_item.setFlags(kind_item.flags() & ~Qt.ItemIsEditable)
            combo = QComboBox()
            available = (
                (BodyRole.PART, BodyRole.IGNORE, BodyRole.UNASSIGNED)
                if body.is_part_eligible
                else (BodyRole.IGNORE, BodyRole.UNASSIGNED)
            )
            for role in available:
                combo.addItem(self._t(f"role_{role.value}"), role.value)
            current = roles.get(body.body_id, BodyRole.UNASSIGNED)
            index = combo.findData(current.value)
            combo.setCurrentIndex(max(0, index))
            self.part_table.setItem(row, 0, name_item)
            self.part_table.setItem(row, 1, kind_item)
            self.part_table.setCellWidget(row, 2, combo)
            self._role_combos[body.body_id] = combo
        apply_tube_help(self)

    def _retranslate_part_roles(self) -> None:
        for combo in self._role_combos.values():
            for index in range(combo.count()):
                combo.setItemText(index, self._t(f"role_{combo.itemData(index)}"))

    def _confirm_part(self) -> None:
        try:
            roles = {body_id: combo.currentData() for body_id, combo in self._role_combos.items()}
            self._execute_command(
                "confirm_part",
                part_body_ids=tuple(
                    key for key, role in roles.items() if role == BodyRole.PART.value
                ),
                ignored_body_ids=tuple(
                    key for key, role in roles.items() if role == BodyRole.IGNORE.value
                ),
            )
            part_ids = self.controller.setup.assignments.part_body_ids
            if hasattr(self.viewer, "set_selection"):
                self.viewer.set_selection(body_ids=list(part_ids))
        except Exception as exc:
            self._report_error(exc)

    def _create_operation(self) -> None:
        try:
            self._execute_command(
                "create_operation",
                operation_type=self.operation_type_combo.currentData(),
            )
        except Exception as exc:
            self._report_error(exc)

    def _apply_machine(self) -> None:
        try:
            profile = self._machine_profiles[str(self.machine_combo.currentData())]
            self._execute_command("set_machine", _resource_profile_id(profile))
            self._reload_resource_catalogs(follow_setup=frozenset(("machine",)))
            self._populate_mounts()
        except Exception as exc:
            self._report_error(exc)

    def _update_machine_detail(self) -> None:
        machine_profile_ui.update_detail(self)

    def _apply_nozzle(self) -> None:
        try:
            template = self._nozzle_profiles[str(self.nozzle_combo.currentData())]
            self._execute_command(
                "set_nozzle",
                _resource_profile_id(template),
                interface=self.nozzle_interface.text(),
                length_mm=self.nozzle_length.value(),
                use_collision_envelope=self.nozzle_collision.isChecked(),
            )
            self._reload_resource_catalogs(follow_setup=frozenset(("nozzle",)))
            _sync_nozzle_editor(self)
        except NozzleEditorError as exc:
            self._report_error(ValueError(self._t(exc.code)))
        except Exception as exc:
            self._report_error(exc)

    def _apply_material(self) -> None:
        try:
            template = self._material_profiles[str(self.material_combo.currentData())]
            self._execute_command(
                "set_material",
                _resource_profile_id(template),
                review_confirmed=self.material_review.isChecked(),
            )
            self._reload_resource_catalogs(follow_setup=frozenset(("material",)))
            _sync_material_editor(self)
        except Exception as exc:
            self._report_error(exc)

    def _update_material_detail(self) -> None:
        profile = self._material_profiles.get(str(self.material_combo.currentData()))
        if profile is None:
            self.material_detail.clear()
            return
        rec = profile.recommendations
        self.material_detail.setText(
            f"{profile.material} · {profile.filament_diameter_mm:.2f} mm\n"
            f"Nozzle {rec.nozzle_temperature_c:.0f} °C · Plate {rec.build_plate_temperature_c:.0f} °C\n"
            f"Revision {profile.source.revision[:12]}"
        )

    def _begin_coordinate_editor(self, node: str) -> None:
        self._coordinate_node = node
        try:
            draft = self.controller.coordinate_draft(node)
        except DraftNotFoundError:
            draft = self.controller.begin_coordinate_draft(node)
        self.coordinate_help.setText(
            self._t("coordinate_help_model" if node == MODEL_CS_NODE else "coordinate_help_build")
        )
        self.coordinate_feedback.setText(
            f"Draft: origin={'✓' if draft.origin_reference else '—'}, "
            f"Z={'✓' if draft.z_direction_reference else '—'}, X={'✓' if draft.x_direction_reference else '—'}"
        )
        self._coordinate_control_dirty.clear()
        self._populate_coordinate_candidates()
        self._sync_coordinate_controls_from_draft(draft)
        self.refresh()

    def _populate_coordinate_candidates(self, *, preserve_selection: bool = False) -> None:
        if not hasattr(self, "coordinate_inputs"):
            return
        combos = {key: controls[0] for key, controls in self.coordinate_inputs.items()}
        selected = (
            {key: _coordinate_candidate_key(combo.currentData()) for key, combo in combos.items()}
            if preserve_selection
            else {}
        )
        origin_combo = combos["origin"]
        direction_combos = (combos["z"], combos["x"])
        for combo in (origin_combo, *direction_combos):
            combo.blockSignals(True)
            combo.clear()
        origin_combo.addItem(self._t("numeric"), {"kind": "numeric"})
        origin_combo.addItem(self._t("pick_vertex"), {"kind": "pick_vertex"})
        origin_combo.addItem(self._t("pick_face"), {"kind": "pick_face"})
        for candidate in self._candidate_payloads.get("origins", []):
            origin_combo.addItem(
                f"{candidate['kind']} · {candidate['entity_id']}",
                dict(candidate),
            )
        for combo in direction_combos:
            combo.addItem(self._t("numeric"), {"kind": "numeric"})
            combo.addItem(self._t("pick_line"), {"kind": "pick_line"})
            combo.addItem(self._t("pick_axis_face"), {"kind": "pick_axis_face"})
            combo.addItem(self._t("pick_two_vertices"), {"kind": "pick_two_vertices"})
            for candidate in self._candidate_payloads.get("directions", []):
                combo.addItem(
                    f"{candidate['kind']} · {candidate['entity_id']}",
                    dict(candidate),
                )
        for component, combo in combos.items():
            target = selected.get(component)
            index = next(
                (
                    item
                    for item in range(combo.count())
                    if _coordinate_candidate_key(combo.itemData(item)) == target
                ),
                0,
            )
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        apply_tube_help(self)

    def _coordinate_candidate_changed(self, component: str) -> None:
        if self._updating_coordinate_controls:
            return
        self._coordinate_control_dirty.add(component)
        combo, values, _pick, _title = self.coordinate_inputs[component]
        data = combo.currentData()
        if not isinstance(data, Mapping):
            return
        resolved = data.get("point" if component == "origin" else "vector")
        if isinstance(resolved, list | tuple) and len(resolved) == 3:
            self._updating_coordinate_controls = True
            try:
                for spin, value in zip(values, resolved, strict=False):
                    spin.setValue(float(value))
            finally:
                self._updating_coordinate_controls = False

    def _coordinate_value_changed(self, component: str) -> None:
        if not self._updating_coordinate_controls:
            self._coordinate_control_dirty.add(component)

    def _sync_coordinate_controls_from_draft(self, draft: Any) -> None:
        references = {
            "origin": draft.origin_reference,
            "z": draft.z_direction_reference,
            "x": draft.x_direction_reference,
        }
        self._updating_coordinate_controls = True
        try:
            for component, reference in references.items():
                combo, values, _pick, _title = self.coordinate_inputs[component]
                selected_index = 0
                resolved = _COORDINATE_DEFAULTS[component]
                if reference is not None:
                    target_kind = reference.reference_type
                    target_id = None if reference.geometry is None else reference.geometry.object_id
                    if target_kind == "face_pick":
                        target_kind = "pick_face"
                        target_id = None
                    elif target_kind == "two_points":
                        target_kind = "pick_two_vertices"
                        target_id = None
                    selected_index = _coordinate_reference_index(combo, target_kind, target_id)
                    resolved = presenter.reference_display_value(
                        self.controller, draft.node, reference
                    )
                combo.setCurrentIndex(selected_index)
                for spin, value in zip(values, resolved, strict=False):
                    spin.setValue(float(value))
        finally:
            self._updating_coordinate_controls = False
        self._coordinate_control_dirty.clear()

    def _set_coordinate_reference_from_controls(self, component: str) -> None:
        combo, values, _pick, _title = self.coordinate_inputs[component]
        data = combo.currentData()
        if not isinstance(data, Mapping):
            raise ValueError("coordinate candidate is invalid")
        kind = str(data.get("kind", "numeric"))
        vector = tuple(spin.value() for spin in values)
        if component == "origin":
            if kind.startswith("pick_"):
                raise ValueError("pick a geometry item in the viewer before confirming")
            if kind == "numeric":
                self.controller.set_numeric_origin(self._coordinate_node, vector)
                return
            geometry = self._geometry_reference(str(data["entity_id"]))
            self.controller.set_origin_reference(
                self._coordinate_node,
                PointReference(kind, vector, geometry=geometry),
            )
            return
        if kind.startswith("pick_"):
            raise ValueError("pick the requested geometry in the viewer before confirming")
        if kind == "numeric":
            self.controller.set_numeric_direction(self._coordinate_node, component, vector)
            return
        geometry = self._geometry_reference(str(data["entity_id"]))
        self.controller.set_direction_reference(
            self._coordinate_node,
            component,
            DirectionReference(kind, vector, geometry=geometry),
        )

    def _confirm_coordinate_component(self, component: str) -> None:
        try:
            try:
                draft = self.controller.coordinate_draft(self._coordinate_node)
            except DraftNotFoundError:
                draft = self.controller.begin_coordinate_draft(self._coordinate_node)
            current = {
                "origin": draft.origin_reference,
                "z": draft.z_direction_reference,
                "x": draft.x_direction_reference,
            }[component]
            if current is None or component in self._coordinate_control_dirty:
                self._set_coordinate_reference_from_controls(component)
            self.controller.confirm_coordinate_reference(self._coordinate_node, component)
            self._coordinate_control_dirty.discard(component)
            self.coordinate_feedback.setText(f"{component.upper()} confirmed")
            self._refresh_overlays()
            self.refresh()
        except Exception as exc:
            self._report_error(exc, self.coordinate_feedback)

    def _flip_coordinate(self, component: str) -> None:
        try:
            try:
                self.controller.coordinate_draft(self._coordinate_node)
            except DraftNotFoundError:
                self.controller.begin_coordinate_draft(self._coordinate_node)
            self.controller.flip_direction(self._coordinate_node, component)
            self._refresh_overlays()
            self.refresh()
        except Exception as exc:
            self._report_error(exc, self.coordinate_feedback)

    def _apply_coordinate(self) -> None:
        try:
            if self._coordinate_control_dirty:
                raise ValueError(self._t("coordinate_reconfirm_error"))
            self._execute_command("apply_coordinate_draft", node=self._coordinate_node)
            frame = (
                self.controller.setup.model_coordinate_system
                if self._coordinate_node == MODEL_CS_NODE
                else self.controller.setup.build_coordinate_system
            )
            if frame is None:  # pragma: no cover - provider contract guard
                raise RuntimeError("coordinate command did not publish an applied frame")
            self.coordinate_feedback.setText(f"Applied {frame.name} · revision {frame.revision}")
        except Exception as exc:
            self._report_error(exc, self.coordinate_feedback)

    def _cancel_coordinate(self) -> None:
        try:
            self.controller.cancel_draft(self._coordinate_node)
        except DraftNotFoundError:
            pass
        _restore_coordinate_editor(self)
        self.coordinate_feedback.clear()
        self.refresh()

    def _start_pick(self, component: str) -> None:
        try:
            self.controller.coordinate_draft(self._coordinate_node)
        except DraftNotFoundError:
            self.controller.begin_coordinate_draft(self._coordinate_node)
        combo = self.coordinate_inputs[component][0]
        data = combo.currentData()
        if not isinstance(data, Mapping):
            return
        kind = str(data.get("kind", "numeric"))
        entity_id = data.get("entity_id")
        allowed = None if entity_id is None else frozenset({str(entity_id)})
        if component == "origin":
            pick_kind = (
                "face"
                if kind == "pick_face"
                else "vertex"
                if kind == "pick_vertex"
                else _entity_kind(str(entity_id))
            )
        elif kind == "pick_two_vertices":
            pick_kind = "vertex"
            self._two_point_hits.clear()
        elif kind == "pick_axis_face":
            pick_kind = "face"
        elif kind == "pick_line":
            pick_kind = "edge"
        else:
            pick_kind = _entity_kind(str(entity_id))
        if pick_kind not in {"face", "edge", "vertex"}:
            raise ValueError("select a geometric candidate before picking")
        self._pick_context = (self._coordinate_node, component, kind)
        if hasattr(self.viewer, "set_pick_request"):
            self.viewer.set_pick_request(
                PickRequest(pick_kind, allowed_ids=allowed, multiple=kind == "pick_two_vertices")
            )
        self.coordinate_feedback.setText(f"Pick {pick_kind}: {component.upper()}")

    def _on_pick_hit(self, hit: PickHit) -> None:
        if self._pick_context is None or self.model is None:
            return
        node, component, requested_kind = self._pick_context
        try:
            geometry = self._geometry_reference(hit.entity_id)
            if component == "origin":
                point_reference = presenter.resolve_origin_pick(
                    self.model, hit, requested_kind, geometry
                )
                self.controller.set_origin_reference(node, point_reference)
            else:
                first_hit = None
                if requested_kind == "pick_two_vertices":
                    self._two_point_hits.append(hit)
                    if len(self._two_point_hits) < 2:
                        self.coordinate_feedback.setText("Pick second vertex")
                        return
                    first_hit = self._two_point_hits[0]
                direction_reference = presenter.resolve_direction_pick(
                    self.model,
                    hit,
                    requested_kind,
                    geometry,
                    first_vertex_hit=first_hit,
                    geometry_resolver=self._geometry_reference,
                )
                self.controller.set_direction_reference(node, component, direction_reference)
            self._finish_pick(hit, component)
        except Exception as exc:
            self._report_error(exc, self.coordinate_feedback)

    def _finish_pick(self, hit: PickHit, component: str) -> None:
        self._pick_context = None
        self._coordinate_control_dirty.discard(component)
        self.coordinate_feedback.setText(f"Picked {hit.entity_id}; confirm {component.upper()}")
        self._refresh_overlays()
        self.refresh()

    def _geometry_reference(self, entity_id: str) -> GeometryReference:
        if self.model is None:
            raise ValueError("no CAD model is loaded")
        if entity_id in self.model.body_map:
            kind = "body" if self.model.body_map[entity_id].is_solid else "shell"
        elif entity_id in self.model.face_map:
            kind = "face"
        elif entity_id in self.model.edge_map:
            kind = "edge"
        elif entity_id in self.model.vertex_map:
            kind = "vertex"
        else:
            raise ValueError(f"unknown CAD entity: {entity_id}")
        return self.controller.geometry_reference(entity_id, kind)

    def _populate_mounts(self) -> None:
        self.mount_combo.blockSignals(True)
        self.mount_combo.clear()
        try:
            profile = self.controller.machine_profile()
        except ValueError:
            profile = None
        if profile is not None:
            for mount in profile.mount_datums:
                self.mount_combo.addItem(mount.name, mount.mount_id)
            current = self.controller.setup.mount_datum_id
            if current:
                self.mount_combo.setCurrentIndex(max(0, self.mount_combo.findData(current)))
        self.mount_combo.blockSignals(False)

    def _begin_placement_editor(self) -> None:
        self._populate_mounts()
        mount_id = self.mount_combo.currentData()
        try:
            draft = self.controller.placement_draft()
        except DraftNotFoundError:
            draft = self.controller.begin_placement_draft(
                mount_datum_id=None if mount_id is None else str(mount_id)
            )
        if draft.mount_datum_id and self.mount_combo.findData(draft.mount_datum_id) >= 0:
            self.mount_combo.setCurrentIndex(self.mount_combo.findData(draft.mount_datum_id))
        translation = draft.adjustment.translation_mm
        angles = draft.adjustment.euler_xyz_rad
        self._updating_placement_controls = True
        try:
            for key, value in zip(("dx", "dy", "dz"), translation, strict=False):
                self.placement_spins[key].setValue(value)
            for key, value in zip(("rx", "ry", "rz"), angles, strict=False):
                self.placement_spins[key].setValue(math.degrees(value))
        finally:
            self._updating_placement_controls = False
        self.refresh()

    def _placement_mount_changed(self) -> None:
        mount_id = self.mount_combo.currentData()
        if mount_id is None:
            return
        try:
            self.controller.set_placement_mount(str(mount_id))
            self._refresh_overlays()
        except DraftNotFoundError:
            return
        except Exception as exc:
            self._report_error(exc, self.placement_feedback)

    def _placement_adjustment_changed(self) -> None:
        if self._updating_placement_controls:
            return
        try:
            self.controller.placement_draft()
        except DraftNotFoundError:
            return
        try:
            translation = tuple(self.placement_spins[key].value() for key in ("dx", "dy", "dz"))
            rotation = tuple(
                math.radians(self.placement_spins[key].value()) for key in ("rx", "ry", "rz")
            )
            self.controller.set_placement_adjustment(translation, rotation)
            self._refresh_overlays()
            self.state_changed.emit(self.controller.state_json())
        except Exception as exc:
            self._report_error(exc, self.placement_feedback)

    def _apply_placement(self) -> None:
        previous_mode = self._view_mode
        try:
            try:
                self.controller.placement_draft()
            except DraftNotFoundError:
                mount_id = self.mount_combo.currentData()
                self.controller.begin_placement_draft(
                    mount_datum_id=None if mount_id is None else str(mount_id)
                )
            translation = tuple(self.placement_spins[key].value() for key in ("dx", "dy", "dz"))
            rotation = tuple(
                math.radians(self.placement_spins[key].value()) for key in ("rx", "ry", "rz")
            )
            self.controller.set_placement_adjustment(translation, rotation)
            self._set_view_mode_state("machine")
            self._execute_command("apply_placement_draft")
            transform = self.controller.setup.T_mount_from_build
            if transform is None:  # pragma: no cover - provider contract guard
                raise RuntimeError("placement command did not publish a transform")
            self.placement_feedback.setText(
                f"Applied T_mount_from_build · ({transform.translation[0]:.3f}, "
                f"{transform.translation[1]:.3f}, {transform.translation[2]:.3f}) mm"
            )
        except Exception as exc:
            self._set_view_mode_state(previous_mode)
            self._report_error(exc, self.placement_feedback)

    def _cancel_placement(self) -> None:
        try:
            self.controller.cancel_draft(PLACEMENT_NODE)
        except DraftNotFoundError:
            pass
        self.placement_feedback.clear()
        self.refresh()

    def set_view_mode(self, mode: str) -> None:
        self._set_view_mode_state(mode)
        self._refresh_overlays()

    def _set_view_mode_state(self, mode: str) -> None:
        if mode not in {"model", "machine"}:
            raise ValueError(f"unsupported Tube view mode: {mode}")
        self._view_mode = mode
        self.model_view_button.setEnabled(mode != "model")
        self.machine_view_button.setEnabled(mode != "machine")

    def _refresh_overlays(self) -> None:
        presentation = presenter.viewer_presentation(
            self.controller,
            has_model=self.model is not None,
            view_mode=self._view_mode,
            active_coordinate_node=self._coordinate_node,
        )
        if hasattr(self.viewer, "set_model_transform"):
            self.viewer.set_model_transform(presentation.model_matrix)
        if hasattr(self.viewer, "set_coordinate_frames"):
            self.viewer.set_coordinate_frames(
                presentation.coordinate_frames,
                active_frame_id=presentation.active_frame_id,
            )
        if hasattr(self.viewer, "set_build_surface"):
            self.viewer.set_build_surface(presentation.build_surface)

    def _jump_to_issue(self) -> None:
        item = self.issue_list.currentItem()
        if item is None:
            return
        payload = item.data(Qt.UserRole)
        if isinstance(payload, Mapping):
            context = payload.get("context", {})
            if isinstance(context, Mapping):
                self.select_setup_node(str(context.get("node", "")))

    def select_setup_node(self, node: str) -> bool:
        item = self._tree_items.get(str(node))
        if item is not None:
            self.tree.setCurrentItem(item)
        return item is not None

    def _report_error(self, error: Exception, target: QLabel | None = None) -> None:
        _publish_error(self, error, target)

    def state_json(self) -> dict[str, Any]:
        state = self.controller.state_json()
        state["view_mode"] = self._view_mode
        return state

    def project_resources(self) -> dict[str, Any]:
        setup = self.controller.setup
        return {
            name: snapshot
            for name, snapshot in (
                ("machine", setup.machine),
                ("nozzle", setup.nozzle),
                ("material", setup.material),
            )
            if snapshot is not None
        }

    def select_builtin_resource(
        self,
        kind: str,
        identifier: str,
        **options: Any,
    ) -> None:
        """Automation-safe adapter for the combined resource catalog."""

        key = str(identifier).strip().lower()
        if kind not in _RESOURCE_KINDS:
            raise ValueError(f"unsupported resource kind: {kind}")
        profiles = getattr(self, f"_{kind}_profiles")
        profile = next((item for item in profiles.values() if _resource_matches(item, key)), None)
        if profile is None:
            raise KeyError(identifier)
        resource_id = _resource_profile_id(profile)
        if kind == "nozzle" and options.get("complete"):
            self._execute_command(
                "set_complete_nozzle",
                resource_id,
                dict(options),
                command_origin="automation",
            )
        elif kind == "material":
            self._execute_command(
                "set_material",
                resource_id,
                command_origin="automation",
                review_confirmed=options.get("review_confirmed"),
            )
        else:
            self._execute_command(f"set_{kind}", resource_id, command_origin="automation")
        self._reload_resource_catalogs(follow_setup=frozenset((kind,)))
        if kind == "nozzle":
            _sync_nozzle_editor(self)
        elif kind == "material":
            _sync_material_editor(self)

    def apply_numeric_coordinate(
        self,
        node: str,
        origin: tuple[float, float, float],
        z_direction: tuple[float, float, float],
        x_direction: tuple[float, float, float],
        *,
        flip_z: bool = False,
        flip_x: bool = False,
    ) -> CoordinateFrameDefinition:
        canonical = str(node).strip().lower()
        if canonical not in {MODEL_CS_NODE, BUILD_CS_NODE}:
            raise ValueError(f"unsupported coordinate node: {node!r}")
        z = tuple(-value for value in z_direction) if flip_z else z_direction
        x = tuple(-value for value in x_direction) if flip_x else x_direction
        self._execute_command(
            "set_model_cs" if canonical == MODEL_CS_NODE else "set_build_cs",
            command_origin="automation",
            origin=origin,
            z=z,
            x=x,
        )
        frame = (
            self.controller.setup.model_coordinate_system
            if canonical == MODEL_CS_NODE
            else self.controller.setup.build_coordinate_system
        )
        if frame is None:  # pragma: no cover - provider contract guard
            raise RuntimeError("coordinate command did not publish an applied frame")
        return frame


def _apply_placement(
    self: TubeSetupPage,
    mount_datum_id: str,
    translation_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation_xyz_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> None:
    previous_mode = self._view_mode
    self._set_view_mode_state("machine")
    try:
        self._execute_command(
            "set_placement",
            mount_datum_id,
            command_origin="automation",
            translation_mm=translation_mm,
            rotation_xyz_deg=rotation_xyz_deg,
        )
    except Exception:
        self._set_view_mode_state(previous_mode)
        raise


TubeSetupPage.apply_placement = _apply_placement


def _help_label() -> QLabel:
    label = QLabel()
    label.setObjectName("mutedText")
    label.setWordWrap(True)
    return label


def _add_operation_footer(page: TubeSetupPage, layout: QVBoxLayout) -> None:
    layout.addWidget(page.operation_feedback)
    layout.addWidget(page.operation_apply_button)
    _set_operation_footer_visible(page, False)


def _set_operation_footer_visible(page: TubeSetupPage, visible: bool) -> None:
    page.operation_feedback.setVisible(visible)
    page.operation_apply_button.setVisible(visible)


def _coordinate_candidate_key(value: Any) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        return "", ""
    return str(value.get("kind", "")), str(value.get("entity_id", ""))


def _coordinate_reference_index(combo: QComboBox, kind: str, object_id: str | None) -> int:
    for index in range(combo.count()):
        candidate_kind, candidate_id = _coordinate_candidate_key(combo.itemData(index))
        if candidate_kind == kind and (object_id is None or candidate_id == object_id):
            return index
    return 0


def _restore_coordinate_editor(page: TubeSetupPage) -> None:
    applied = (
        page.controller.setup.model_coordinate_system
        if page._coordinate_node == MODEL_CS_NODE
        else page.controller.setup.build_coordinate_system
    )
    page._populate_coordinate_candidates()
    page._sync_coordinate_controls_from_draft(
        CoordinateFrameDraft.from_applied(page._coordinate_node, applied)
    )


def _resource_profile_id(
    profile: MachineProfile | NozzleProfile | MaterialProfile,
) -> str:
    return profile.profile_id if isinstance(profile, MachineProfile) else profile.resource_id


def _resource_matches(
    profile: MachineProfile | NozzleProfile | MaterialProfile,
    key: str,
) -> bool:
    labels = [_resource_profile_id(profile).lower()]
    if isinstance(profile, MachineProfile):
        labels.append(profile.name.lower())
    elif isinstance(profile, NozzleProfile):
        labels.extend((f"{profile.orifice_diameter_mm:g}", profile.display_name.lower()))
    else:
        labels.extend((profile.material.lower(), profile.display_name.lower()))
    return bool(key) and any(key in label for label in labels)


def _publish_error(
    page: TubeSetupPage,
    error: Exception,
    target: QLabel | None,
) -> None:
    message = str(error)
    if target is not None:
        target.setText(message)
    page.error_raised.emit(message)


def _sync_nozzle_editor(page: TubeSetupPage) -> None:
    profile = page._nozzle_profiles.get(str(page.nozzle_combo.currentData()))
    if profile is None:
        return
    page.nozzle_interface.setText(profile.interface or "")
    page.nozzle_length.setValue(profile.length_mm or 0.0)
    page.nozzle_collision.setChecked(bool(profile.outer_profile_rz_mm))


def _sync_material_editor(page: TubeSetupPage) -> None:
    profile = page._material_profiles.get(str(page.material_combo.currentData()))
    page.material_review.setChecked(bool(profile and profile.review_confirmed))
    page._update_material_detail()


def _profile_from_snapshot(
    kind: str,
    snapshot: ResourceSnapshot,
) -> MachineProfile | NozzleProfile | MaterialProfile:
    if kind == "machine":
        return MachineProfile.from_json(snapshot.payload)
    if kind == "nozzle":
        return snapshot.as_nozzle_profile()
    if kind == "material":
        return snapshot.as_material_profile()
    raise ValueError(f"unsupported resource kind: {kind}")


def _matching_profile_key(
    kind: str,
    snapshot: ResourceSnapshot,
    profiles: Mapping[str, Any],
) -> str | None:
    for key, profile in profiles.items():
        try:
            candidate = ResourceSnapshot.capture(kind, profile)
        except (TypeError, ValueError):
            continue
        if candidate.content_hash == snapshot.content_hash:
            return key
    return None


def _entity_kind(entity_id: str) -> str:
    for kind in ("face", "edge", "vertex"):
        if f"_{kind}_" in entity_id:
            return kind
    return ""


def _state_color(state: NodeState) -> QColor:
    return {
        NodeState.MISSING: QColor("#C27825"),
        NodeState.DRAFT: QColor("#8B5CF6"),
        NodeState.VALID: QColor("#20815D"),
        NodeState.DIRTY: QColor("#B7791F"),
        NodeState.INVALID: QColor("#C43D4E"),
    }[state]


__all__ = ["TubeSetupPage"]
