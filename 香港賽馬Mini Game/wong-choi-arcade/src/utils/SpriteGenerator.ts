// Generates Base64 PNGs from ASCII art for our retro arcade feel!

function createPixelTexture(ascii: string[], colorMap: Record<string, string>, scale = 4): string {
    const height = ascii.length;
    const width = ascii[0].length;
    
    const canvas = document.createElement('canvas');
    canvas.width = width * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext('2d')!;
    
    // Clear background
    ctx.clearRect(0,0, canvas.width, canvas.height);

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const char = ascii[y][x];
        if (colorMap[char]) {
          ctx.fillStyle = colorMap[char];
          ctx.fillRect(x * scale, y * scale, scale, scale);
        }
      }
    }
    return canvas.toDataURL('image/png');
}

// 32x24 pixel art horse frames (4-frame cycle for realistic gallop)
// H=Body, M=Mane/Tail, E=Eye, D=Darker Shading (Legs further away), L=Hoof, J=Jockey Body, S=Jockey Silks, K=Jockey Helmet
const FRAMES = [
  // Frame 1: Stretched out
  [
    "                                ",
    "                                ",
    "          K                     ",
    "         KSS                    ",
    "        KSSSS                   ",
    "        JJSSJ       MM          ",
    "       JH  J       MMM          ",
    "       J    JJJJJ  MHHM         ",
    "            HJJSSM MHHEHM       ",
    "       HHHHHHHHHHHHHHHHHH       ",
    "      HHHHHHHHHHHHHHHHHH        ",
    "     MHHHHHHHHHHHHHHHHH         ",
    "    MHHHHHHHHHHHHHHH            ",
    "   MHHHHHHHHHHH  HHH            ",
    "    DD D      H    H            ",
    "    D  D      H     H           ",
    "    D  D       H     H          ",
    "   L  L        L      L         ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                "
  ],
  // Frame 2: Gathering
  [
    "                                ",
    "          K                     ",
    "         KSS                    ",
    "        KSSSS                   ",
    "        JJSSJ       MM          ",
    "       JH  J       MMM          ",
    "      J     JJJJJ MHHH          ",
    "           HJJSSMMHEEH          ",
    "      HHHHHHHHHHHHHHHH          ",
    "     HHHHHHHHHHHHHHH            ",
    "    MHHHHHHHHHHHHHHH            ",
    "   MHHHHHHHHHHHHHH              ",
    "   MHHHHHHHHH HHH               ",
    "    DD D     HH  H              ",
    "   D  D      H   H              ",
    "   D  D       H  H              ",
    "   L   L      LL H              ",
    "                  L             ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                "
  ],
  // Frame 3: Contracted (Airborne)
  [
    "                                ",
    "          K          MM         ",
    "         KSS        MMM         ",
    "        KSSSS      MHHM         ",
    "        JJSSJ      MHEHM        ",
    "       JH  J      MHHHH         ",
    "      J     JJJJJHHHHH          ",
    "           HJJSSHHHHH           ",
    "      HHHHHHHHHHHHHH            ",
    "     MMHHHHHHHHHHHHH            ",
    "    MMMHHHHHHHHHHHH             ",
    "   MMMHHHHHHHHHHHH              ",
    "    HHH   HHH HHH               ",
    "     D    D  H   HH             ",
    "    D    D    H    H            ",
    "    L    D    H     H           ",
    "         L     L     L          ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                "
  ],
  // Frame 4: Pushing off
  [
    "                                ",
    "                                ",
    "          K          M          ",
    "         KSS        MM          ",
    "        KSSSS      MHHM         ",
    "        JJSSJ      MEEHM        ",
    "       JH  J     MHHHHHH        ",
    "      J     JJJJJHHHHHH         ",
    "           HJJSSHHHHHH          ",
    "      HHHHHHHHHHHHHHH           ",
    "     MHHHHHHHHHHHHHHH           ",
    "    MHHHHHHHHHHHHHHHH           ",
    "   MHHHHHHHHHHHHH HHH           ",
    "    D    D    HH  H  H          ",
    "   D    D      H   H H          ",
    "   D    D      H   H H          ",
    "   L     L      L   L L         ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                ",
    "                                "
  ]
];

// Combine horse and jockey into one frame generation
export const generateCombinedFrames = () => {
    return FRAMES.map(frame => createPixelTexture(frame, {
        'H': '#FFFFFF', // Horse Body (Tintable!)
        'D': '#AAAAAA', // Far horse legs (Tintable but darker implicitly via alpha overlay later or just grey for now)
        'M': '#222222', // Mane/Tail
        'E': '#000000', // Eye
        'L': '#111111', // Hoof
        
        'K': '#CC0000', // Jockey Helmet
        'S': '#00AADD', // Silks
        'J': '#EEEEEE', // Pants/Boots/Skin
    }, 4)); // 4x scale
};

// Generate a soft transparent ellipse for shadows
export const generateShadowTexture = (): string => {
    const canvas = document.createElement('canvas');
    canvas.width = 120;
    canvas.height = 40;
    const ctx = canvas.getContext('2d')!;
    
    ctx.beginPath();
    ctx.ellipse(60, 20, 50, 15, 0, 0, 2 * Math.PI);
    ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
    ctx.fill();
    
    return canvas.toDataURL('image/png');
};

