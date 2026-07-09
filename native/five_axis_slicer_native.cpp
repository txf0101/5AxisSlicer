#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

namespace py = pybind11;

py::dict build_preview_index(
    py::array_t<std::int32_t, py::array::c_style | py::array::forcecast> timeline_layers,
    py::array_t<std::int32_t, py::array::c_style | py::array::forcecast> segment_step_indices,
    int layer_min,
    int layer_max
) {
    auto timeline = timeline_layers.unchecked<1>();
    auto segment_steps = segment_step_indices.unchecked<1>();

    int layer_count = std::max(0, layer_max - layer_min + 1);
    std::vector<std::int32_t> counts(static_cast<std::size_t>(layer_count), 0);
    for (py::ssize_t index = 0; index < timeline.shape(0); ++index) {
        int layer = timeline(index);
        if (layer >= layer_min && layer <= layer_max) {
            counts[static_cast<std::size_t>(layer - layer_min)] += 1;
        }
    }

    py::array_t<std::int32_t> prefix({layer_count + 1});
    auto prefix_mut = prefix.mutable_unchecked<1>();
    prefix_mut(0) = 0;
    for (int index = 0; index < layer_count; ++index) {
        prefix_mut(index + 1) = prefix_mut(index) + counts[static_cast<std::size_t>(index)];
    }

    py::array_t<std::int32_t> timeline_indices({prefix_mut(layer_count)});
    auto timeline_indices_mut = timeline_indices.mutable_unchecked<1>();
    std::vector<std::int32_t> cursor(static_cast<std::size_t>(layer_count), 0);
    for (int index = 0; index < layer_count; ++index) {
        cursor[static_cast<std::size_t>(index)] = prefix_mut(index);
    }
    for (py::ssize_t index = 0; index < timeline.shape(0); ++index) {
        int layer = timeline(index);
        if (layer < layer_min || layer > layer_max) {
            continue;
        }
        int offset = layer - layer_min;
        std::int32_t write_at = cursor[static_cast<std::size_t>(offset)]++;
        timeline_indices_mut(write_at) = static_cast<std::int32_t>(index);
    }

    py::array_t<std::int32_t> segment_steps_out({segment_steps.shape(0)});
    py::array_t<std::int32_t> segment_indices({segment_steps.shape(0)});
    auto segment_steps_out_mut = segment_steps_out.mutable_unchecked<1>();
    auto segment_indices_mut = segment_indices.mutable_unchecked<1>();
    for (py::ssize_t index = 0; index < segment_steps.shape(0); ++index) {
        segment_steps_out_mut(index) = segment_steps(index);
        segment_indices_mut(index) = static_cast<std::int32_t>(index);
    }

    py::dict result;
    result["layer_prefix_counts"] = prefix;
    result["timeline_indices"] = timeline_indices;
    result["segment_step_indices"] = segment_steps_out;
    result["segment_indices"] = segment_indices;
    result["source"] = py::str("native");
    return result;
}

PYBIND11_MODULE(five_axis_slicer_native, m) {
    m.doc() = "Native preview index packing for 5AxisSclicer.";
    m.def("build_preview_index", &build_preview_index, py::arg("timeline_layers"), py::arg("segment_step_indices"), py::arg("layer_min"), py::arg("layer_max"));
}
