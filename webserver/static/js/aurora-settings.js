// Store default values
let defaultSettings = {
    brightness: -11,
    saturation: 255,
    contrast: 130,
    hue: 0,
    gamma: 1.0,
    dark_threshold: 20
};

// Load current config on page load
$(document).ready(function() {
    loadCurrentConfig();
});

function loadCurrentConfig() {
    $.ajax({
        url: "/get_config",
        method: "GET",
        contentType: "application/json",
        success: function(response) {
            if (response.status === "success") {
                const config = response.config;
                
                // Update sliders with current values
                $('#hdmi_brightness').slider('setValue', config.hdmi.brightness);
                $('#hdmi_saturation').slider('setValue', config.hdmi.saturation);
                $('#hdmi_contrast').slider('setValue', config.hdmi.contrast);
                $('#hdmi_hue').slider('setValue', config.hdmi.hue);
                $('#aurora_gamma').slider('setValue', config.aurora.gamma);
                $('#aurora_dark_threshold').slider('setValue', config.aurora.dark_threshold);
                
                // Update value displays
                updateValueDisplays();
            }
        },
        error: function(xhr, status, error) {
            showMessage("Error loading configuration: " + error, "error");
        }
    });
}

function updateValueDisplays() {
    $('#brightness_value').text($('#hdmi_brightness').val());
    $('#saturation_value').text($('#hdmi_saturation').val());
    $('#contrast_value').text($('#hdmi_contrast').val());
    $('#hue_value').text($('#hdmi_hue').val());
    $('#gamma_value').text($('#aurora_gamma').val());
    $('#dark_threshold_value').text($('#aurora_dark_threshold').val());
}

// Update value displays when sliders move
$('#hdmi_brightness').on("slide", function(event) {
    $('#brightness_value').text(event.value);
});

$('#hdmi_saturation').on("slide", function(event) {
    $('#saturation_value').text(event.value);
});

$('#hdmi_contrast').on("slide", function(event) {
    $('#contrast_value').text(event.value);
});

$('#hdmi_hue').on("slide", function(event) {
    $('#hue_value').text(event.value);
});

$('#aurora_gamma').on("slide", function(event) {
    $('#gamma_value').text(event.value);
});

$('#aurora_dark_threshold').on("slide", function(event) {
    $('#dark_threshold_value').text(event.value);
});

// Save button click
$('#save_settings_button').on("click", function(event) {
    event.preventDefault();
    
    const settings = {
        brightness: parseInt($('#hdmi_brightness').val()),
        saturation: parseInt($('#hdmi_saturation').val()),
        contrast: parseInt($('#hdmi_contrast').val()),
        hue: parseInt($('#hdmi_hue').val()),
        gamma: parseFloat($('#aurora_gamma').val()),
        dark_threshold: parseInt($('#aurora_dark_threshold').val())
    };
    
    $.ajax({
        url: "/update_aurora_config",
        method: "POST",
        contentType: "application/json",
        data: JSON.stringify(settings),
        success: function(response) {
            if (response.status === "success") {
                showMessage("Settings saved successfully!", "success");
            } else {
                showMessage("Error saving settings: " + response.message, "error");
            }
        },
        error: function(xhr, status, error) {
            showMessage("Error: " + error, "error");
        }
    });
});

// Reset button click
$('#reset_button').on("click", function(event) {
    event.preventDefault();
    
    if (confirm("Are you sure you want to reset all settings to defaults?")) {
        $('#hdmi_brightness').slider('setValue', defaultSettings.brightness);
        $('#hdmi_saturation').slider('setValue', defaultSettings.saturation);
        $('#hdmi_contrast').slider('setValue', defaultSettings.contrast);
        $('#hdmi_hue').slider('setValue', defaultSettings.hue);
        $('#aurora_gamma').slider('setValue', defaultSettings.gamma);
        $('#aurora_dark_threshold').slider('setValue', defaultSettings.dark_threshold);
        
        updateValueDisplays();
        showMessage("Settings reset to defaults. Click 'Save Settings' to apply.", "info");
    }
});

function showMessage(message, type) {
    const alertBox = $('#status_message');
    const alertText = $('#status_text');
    
    // Set message
    alertText.text(message);
    
    // Set color based on type
    alertBox.removeClass('bg-blue-dark bg-red-dark bg-green-dark bg-orange-dark');
    if (type === "success") {
        alertBox.addClass('bg-green-dark');
        alertBox.find('.alert-icon i').attr('class', 'fa fa-check-circle');
    } else if (type === "error") {
        alertBox.addClass('bg-red-dark');
        alertBox.find('.alert-icon i').attr('class', 'fa fa-exclamation-triangle');
    } else if (type === "info") {
        alertBox.addClass('bg-blue-dark');
        alertBox.find('.alert-icon i').attr('class', 'fa fa-info-circle');
    }
    
    // Show and auto-hide after 3 seconds
    alertBox.fadeIn();
    setTimeout(function() {
        alertBox.fadeOut();
    }, 3000);
}
