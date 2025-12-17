import threading
import time
from gpiozero import LED as GPIOZeroLED


class BrightnessLed:
    """
    Drop-in replacement for gpiozero LED class with brightness control.
    Uses software PWM to control LED brightness.
    
    Args:
        pin: GPIO pin number
        frequency: PWM frequency in Hz (default 100Hz, stops visible flickering)
        brightness: Initial brightness 0.0-1.0 (default 1.0)
    """
    
    def __init__(self, pin, frequency: float = 100.0, brightness: float = 1.0):
        self._pin = pin
        self._frequency = frequency
        self._brightness = max(0.0, min(1.0, brightness))  # Clamp to 0-1
        self._is_on = False
        self._led = GPIOZeroLED(self._pin)
        
        # PWM threading
        self._pwm_thread = None
        self._pwm_running = False
        self._lock = threading.Lock()
    
    @property
    def brightness(self) -> float:
        """Get current brightness (0.0-1.0)."""
        return self._brightness
    
    @brightness.setter
    def brightness(self, value: float):
        """Set brightness (0.0-1.0)."""
        self._brightness = max(0.0, min(1.0, value))
        # If LED is on, restart PWM with new brightness
        if self._is_on:
            self._restart_pwm()
    
    @property
    def frequency(self) -> float:
        """Get PWM frequency in Hz."""
        return self._frequency
    
    @frequency.setter
    def frequency(self, value: float):
        """Set PWM frequency in Hz."""
        self._frequency = max(1.0, value)
        if self._is_on:
            self._restart_pwm()
    
    def _pwm_loop(self):
        """Software PWM loop running in background thread."""
        while self._pwm_running:
            with self._lock:
                brightness = self._brightness
                frequency = self._frequency
            
            # Calculate timings
            period_sec = 1.0 / frequency
            on_time = period_sec * brightness
            off_time = period_sec - on_time
            
            # Full brightness - just stay on
            if brightness >= 1.0:
                self._led.on()
                time.sleep(0.01)  # Small sleep to allow checking _pwm_running
                continue
            
            # Zero brightness - just stay off
            if brightness <= 0.0:
                self._led.off()
                time.sleep(0.01)
                continue
            
            # PWM cycle
            if on_time > 0:
                self._led.on()
                time.sleep(on_time)
            
            if off_time > 0 and self._pwm_running:
                self._led.off()
                time.sleep(off_time)
    
    def _start_pwm(self):
        """Start the PWM background thread."""
        if self._pwm_thread is not None and self._pwm_thread.is_alive():
            return
        
        self._pwm_running = True
        self._pwm_thread = threading.Thread(target=self._pwm_loop, daemon=True)
        self._pwm_thread.start()
    
    def _stop_pwm(self):
        """Stop the PWM background thread."""
        self._pwm_running = False
        if self._pwm_thread is not None:
            self._pwm_thread.join(timeout=0.2)
            self._pwm_thread = None
        self._led.off()
    
    def _restart_pwm(self):
        """Restart PWM with updated settings."""
        # No need to restart thread, just update values (lock handles it)
        pass
    
    def on(self, brightness: float = None):
        """
        Turn the LED on.
        
        Args:
            brightness: Optional brightness value 0.0-1.0. If not specified,
                       uses the current brightness setting.
        """
        if brightness is not None:
            with self._lock:
                self._brightness = max(0.0, min(1.0, brightness))
        
        self._is_on = True
        self._start_pwm()
    
    def off(self):
        """Turn the LED off."""
        self._is_on = False
        self._stop_pwm()
    
    def toggle(self):
        """Toggle the LED on/off."""
        if self._is_on:
            self.off()
        else:
            self.on()
    
    def is_on(self) -> bool:
        """Check if LED is currently on."""
        return self._is_on
    
    def close(self):
        """Clean up resources."""
        self.off()
        self._led.close()
    
    def __del__(self):
        """Destructor to clean up."""
        try:
            self.close()
        except Exception:
            pass


# Alias for drop-in replacement
LED = BrightnessLed
