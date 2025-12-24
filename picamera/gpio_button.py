"""
GPIO button handler module using GPIO Zero.
Listens for button presses and triggers a callback.

Usage:
    from gpio_button import GPIOButton

    def on_press():
        print("Button pressed!")

    gpio = GPIOButton(pin=17, callback=on_press)
    gpio.start()
"""

import time

try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False


class GPIOButton:
    """
    GPIO button handler using GPIO Zero.

    Args:
        pin: GPIO pin number (BCM numbering)
        callback: Function to call when button is pressed
        debounce_time: Minimum time between presses (seconds)
    """

    def __init__(self, pin: int = 17, callback=None, debounce_time: float = 0.05):
        self.pin = pin
        self.callback = callback
        self.debounce_time = debounce_time
        self._running = False
        self._button = None

    def _button_callback(self):
        """Internal callback."""
        if self.callback:
            try:
                self.callback()
            except Exception as e:
                print(f"Button callback error: {e}")

    def start(self) -> bool:
        """
        Start listening for button presses.

        Returns:
            True if successful, False if GPIO not available
        """
        if not GPIO_AVAILABLE:
            print("GPIO not available")
            return False

        if self._running:
            return True

        try:
            self._button = Button(self.pin, pull_up=True, bounce_time=self.debounce_time)
            self._button.when_pressed = self._button_callback
            self._running = True
            print(f"GPIO button listening on pin {self.pin}")
            return True
        except Exception as e:
            print(f"Failed to setup GPIO: {e}")
            return False

    def stop(self):
        """Stop listening and clean up GPIO."""
        if self._running and self._button:
            try:
                self._button.close()
            except Exception:
                pass
            self._button = None
            self._running = False

    def is_running(self) -> bool:
        return self._running


# ============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ============================================================================

_button = None


def setup_button(pin: int = 17, callback=None, debounce_time: float = 0.05) -> bool:
    """
    Setup the global button instance.

    Args:
        pin: GPIO pin number
        callback: Function to call on button press
        debounce_time: Debounce time in seconds

    Returns:
        True if successful
    """
    global _button
    _button = GPIOButton(pin=pin, callback=callback, debounce_time=debounce_time)
    return _button.start()


def cleanup_button():
    """Clean up the global button instance."""
    global _button
    if _button:
        _button.stop()
        _button = None


def is_gpio_available() -> bool:
    """Check if GPIO is available."""
    return GPIO_AVAILABLE
