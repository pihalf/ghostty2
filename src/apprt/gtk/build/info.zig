const builtin = @import("builtin");

/// Base application ID
pub const base_application_id = "io.github.pihalf.ghostty2";

/// GTK application ID
pub const application_id = switch (builtin.mode) {
    .debug, .safe => base_application_id ++ "-debug",
    .fast, .small => base_application_id,
};

pub const resource_path = "/io/github/pihalf/ghostty2";

/// GTK object path
pub const object_path = switch (builtin.mode) {
    .debug, .safe => resource_path ++ "_debug",
    .fast, .small => resource_path,
};
