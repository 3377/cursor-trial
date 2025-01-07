/**
 * Special thanks to https://github.com/hmhm2022/gpt-cursor-auto
 * for their Turnstile verification implementation
 */

const getRandomInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

const screenCoords = {
    x: getRandomInt(800, 1200),
    y: getRandomInt(400, 600)
};

Object.defineProperties(MouseEvent.prototype, {
    screenX: { value: screenCoords.x },
    screenY: { value: screenCoords.y }
});