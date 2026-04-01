import { useEffect, useRef } from 'react';
import { Application, Container, Sprite, Texture, Text, TextStyle, AnimatedSprite, Assets, Graphics } from 'pixi.js';
import type { RunnerState, RacePhase } from '../game/GameEngine';
import { generateCombinedFrames, generateShadowTexture } from '../utils/SpriteGenerator';

interface PixiAppProps {
  runners: RunnerState[];
  phase: RacePhase;
  distance: number;
  environment: { venue: 'shatin'|'happy_valley', surface: 'turf'|'dirt' };
}

export default function PixiApp({ runners, phase, distance, environment }: PixiAppProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  
  // Storage for complex objects
  const spritesRef = useRef<Record<number, { 
      container: Container, 
      shadow: Sprite,
      horseAnim: AnimatedSprite, 
      text: Text,
      dusts: Graphics[]
  }>>({});
  
  const cameraRef = useRef<Container | null>(null);
  const parallaxRef = useRef<{ sky: Sprite, mountains: Graphics, ground: Graphics, rails: Graphics } | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    let isCancelled = false;

    const initPixi = async () => {
      // 1. DETERMINE COLORS based on environment
      const isNight = environment.venue === 'happy_valley';
      const isDirt = environment.surface === 'dirt';
      
      const skyBits = isNight ? { bg: 0x05051a, tint: 0x0a092d } : { bg: 0x87ceeb, tint: 0x87ceeb };
      
      const app = new Application();
      await app.init({ 
        width: 800, 
        height: 400, 
        backgroundColor: skyBits.bg, 
        antialias: false,
        resolution: window.devicePixelRatio || 1,
      });
      
      if (isCancelled) {
          app.destroy(true);
          return;
      }
      containerRef.current?.appendChild(app.canvas);
      appRef.current = app;

      // ---- 1. Parallax Background Layer ----
      const bgContainer = new Container();
      app.stage.addChild(bgContainer);
      
      const sky = new Sprite(Texture.WHITE);
      sky.tint = skyBits.tint;
      sky.width = 800; sky.height = 150;
      bgContainer.addChild(sky);

      // Mountains / Cityscape
      const mountains = new Graphics();
      if (isNight) {
          // Happy Valley Night City
          mountains.tint = 0x111133; // dark blue silhouette
          for(let i=0; i<40; i++) {
              let w = 40 + Math.random()*60;
              let h = 30 + Math.random()*70;
              mountains.rect(i*40, 150-h, w, h).fill(0x1a1a40);
              // Windows
              if (Math.random() > 0.3) {
                  mountains.rect(i*40+10, 150-h+10, 4, 4).fill(0xffeaa7);
                  mountains.rect(i*40+20, 150-h+20, 4, 4).fill(0xffeaa7);
              }
          }
      } else {
          // Sha Tin Mountains
          mountains.tint = 0x2d6a4f;
          for(let i=0; i<15; i++) {
              mountains.circle(i*120, 150, 60 + Math.random()*40).fill(0x2d6a4f);
          }
      }
      mountains.y = 0; // The shapes are drawn around 150 already
      bgContainer.addChild(mountains);

      // ---- 2. Camera / 2.5D Track Layer ----
      const camera = new Container();
      app.stage.addChild(camera);
      cameraRef.current = camera;
      
      // Grass Track (striped for speed sensation)
      const ground = new Graphics();
      
      const colors = isDirt 
          ? { dark: 0x6b4226, light: 0x8b5a2b } // Dirt
          : (isNight ? { dark: 0x1e4632, light: 0x2c6046 } : { dark: 0x2d6a4f, light: 0x40916c }); // Night Turf vs Day Turf

      // Draw alternating stripes for 3000m
      for (let i = -1000; i < distance + 1000; i += 200) {
          ground.rect(i, 0, 100, 400).fill(colors.light);
          ground.rect(i + 100, 0, 100, 400).fill(colors.dark); 
      }
      ground.y = 150;
      camera.addChild(ground);

      // White inner rail (posts)
      const rails = new Graphics();
      for (let i = -1000; i < distance + 1000; i += 100) {
          rails.rect(i, 0, 4, -40).fill(0xffffff); // vertical post
          rails.rect(i, -40, 100, 4).fill(0xe0e0e0); // horizontal rail
      }
      rails.y = 150;
      camera.addChild(rails);

      // Finish Line Marker
      const finishLine = new Graphics();
      finishLine.rect(distance, 0, 20, 400).fill(0xff0000); // Red line
      finishLine.rect(distance + 5, 0, 10, 400).fill(0xffffff); // White center
      finishLine.y = 150;
      camera.addChild(finishLine);

      parallaxRef.current = { sky, mountains, ground, rails };

      const textStyle = new TextStyle({ fontSize: 14, fill: 0xffffff, fontWeight: 'bold', stroke: { color: 0x000000, width: 3 } });
      const finishText = new Text({ text: "FINISH LINE", style: textStyle });
      finishText.x = distance - 45; finishText.y = 130;
      camera.addChild(finishText);
      
      // Load generated textures
      const horseBase64Data = generateCombinedFrames();
      const horseTextures = await Promise.all(horseBase64Data.map(d => Assets.load(d)));
      
      const shadowBase64 = generateShadowTexture();
      const shadowTex = await Assets.load(shadowBase64);

      // Pre-create our 12 animated sprites
      runners.forEach(r => {
           const c = new Container();
           
           const shadow = new Sprite(shadowTex);
           shadow.anchor.set(0.5, 0.5);
           shadow.y = 35; // Put shadow at the feet

           const horse = new AnimatedSprite(horseTextures);
           horse.anchor.set(0.5, 0.5);
           horse.animationSpeed = 0; // Driven by game speed
           horse.play();
           
           const nameText = new Text({ text: `${r.competitor.id}. ${r.competitor.horse.name.zh}`, style: textStyle });
           nameText.anchor.set(0.5);
           nameText.y = -45;

           c.addChild(shadow);
           
           // Create simple hoof dust particles
           const dusts: Graphics[] = [];
           const dustColor = environment.surface === 'dirt' ? 0x8b5a2b : 0xEEEEEE;
           for (let i=0; i<4; i++) {
               const d = new Graphics();
               d.circle(0, 0, 3 + Math.random() * 5).fill(dustColor);
               d.alpha = 0;
               c.addChild(d);
               dusts.push(d);
           }

           c.addChild(horse);
           c.addChild(nameText);
           
           camera.addChild(c);
           spritesRef.current[r.competitor.id] = { container: c, shadow, horseAnim: horse, text: nameText, dusts };
      });

      // Apply 2.5D Skew to the ground and rails only, keeping camera flat so sprites stand upright
      ground.skew.x = -0.5;
      rails.skew.x = -0.5;
      finishLine.skew.x = -0.5;
    };

    initPixi();

    return () => {
      isCancelled = true;
      if (appRef.current && appRef.current.canvas) {
        if (containerRef.current?.contains(appRef.current.canvas)) {
             containerRef.current.removeChild(appRef.current.canvas);
        }
        appRef.current.destroy(true, { children: true });
        appRef.current = null;
      }
    };
  }, [distance]);

  // Natively update positions on every React prop change
  useEffect(() => {
    if (!appRef.current || !cameraRef.current) return;
    
    // Y-sorting: sort runners container children based on lane
    const sortedRunners = [...runners].sort((a,b) => a.position.y - b.position.y);
    
    sortedRunners.forEach(r => {
       const obj = spritesRef.current[r.competitor.id];
       if (!obj) return;
       
       // Bring to front based on lane (higher Y = further out/closer to camera bottom)
       cameraRef.current!.setChildIndex(obj.container, cameraRef.current!.children.length - 1);

       obj.container.x = r.position.x;
       
       // Perspective Depth Scaling (Outer lanes are larger, inner lanes smaller)
       // Lane 1 (y=1) -> top of track, smallest
       // Lane 12 (y=12) -> bottom of track, largest
       const depthScale = 0.6 + (r.position.y / 12) * 0.6; // 0.6x to 1.2x
       obj.container.scale.set(depthScale);
       
       // Y Pos mapping: Track starts ~Y=160, ends ~Y=360
       obj.container.y = 160 + (r.position.y * 15);

       // Tint logic for Top 3
       let color = 0xFFFFFF; // default White body
       if (r.placement === 1) color = 0xFFD700; // Gold
       else if (r.placement === 2) color = 0xC0C0C0; // Silver
       else if (r.placement === 3) color = 0xCD7F32; // Bronze
       
       if (r.isStumbling) {
           color = 0x4444FF; // Turn bright blue when stumbling
           obj.text.text = `⚠️失蹄 STUMBLE!`;
           obj.text.style.fill = 0xFF4444;
       } else {
           obj.text.text = `${r.competitor.id}. ${r.competitor.horse.name.zh}`;
           obj.text.style.fill = 0xFFFFFF;
       }
       
       obj.horseAnim.tint = color;

       // Set animation speed proportional to physical speed
       const animRate = r.currentSpeed * 0.006;
       obj.horseAnim.animationSpeed = animRate;
       
       if (r.position.x >= distance + 50) {
           obj.horseAnim.stop();
       } else {
           if (!obj.horseAnim.playing) obj.horseAnim.play();
           
           // Update Dust Particles
           obj.dusts.forEach(d => {
               d.x -= (r.currentSpeed * 0.1) + Math.random() * 2; // drift backwards
               d.y -= 1 + Math.random() * 2; // float up
               d.alpha -= 0.05 + Math.random() * 0.05; // fade out
               
               // Respawn dust if moving fast and faded out
               if (d.alpha <= 0 && r.currentSpeed > 5 && Math.random() < 0.15) {
                   d.x = -15 + Math.random() * 10; // at back hoof
                   d.y = 35 + Math.random() * 5; // at ground level
                   d.alpha = 0.5 + Math.random() * 0.3; // Random opacity
               }
           });
       }
    });

    // Camera Panning
    const leaderX = Math.max(...runners.map(r => r.position.x), 0);
    // Pan so leader is slightly right of center
    const targetCameraX = Math.max(0, leaderX - 500); 
    
    // Smooth camera lag
    cameraRef.current.x += (-targetCameraX - cameraRef.current.x) * 0.1;

    if (parallaxRef.current) {
        // Mountains move parallax (slowly)
        parallaxRef.current.mountains.x = (cameraRef.current.x * 0.2) % 800;
        // Sky moves very slowly
        parallaxRef.current.sky.x = (cameraRef.current.x * 0.05) % 800;
    }

    // Dynamic camera zooming on Sprint phase!
    const targetScale = phase === 'FINAL_SPRINT' ? 1.1 : 1.0;
    cameraRef.current.scale.set(
        cameraRef.current.scale.x + (targetScale - cameraRef.current.scale.x) * 0.05
    );
    // If we scale up, we adjust Y so we don't zoom out of track
    if (phase === 'FINAL_SPRINT') {
        cameraRef.current.y += (-20 - cameraRef.current.y) * 0.05;
    } else {
        cameraRef.current.y += (0 - cameraRef.current.y) * 0.05;
    }

  }, [runners, phase]);

  return <div ref={containerRef} style={{ border: '4px solid #333', borderRadius: 8, overflow: 'hidden', width: 800, height: 400 }} />;
}
