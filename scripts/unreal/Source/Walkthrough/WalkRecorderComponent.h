#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "WalkRecorderComponent.generated.h"

class UCameraComponent;
class AWalkSun;

/**
 * Records a camera route into numbered PNG frames, for videos, fly-ins, AI restyling and scroll pages.
 * Put it on the player pawn (AWalkCharacter has one). It does nothing unless the command line has
 *   -WalkOut=<dir> -WalkRoute=<route.txt>
 * and optionally -WalkFps=24 -WalkFov=84 (horizontal degrees) -WalkWarm=20 (seconds of game time before the
 * first frame: shaders, Lumen and exposure settle) -WalkSub=1 (engine frames per saved frame: more history
 * for Lumen and TSR) -WalkHour=15 -WalkDay=172 -WalkEv=0 -WalkWhite=6500.
 *
 * Route lines (docs/00-interfaces.md), model metres:
 *   key   <t> <eye x y z> <look x y z>
 *   door  <t> <x y z> <radius> open|close     t < 0: before the warm-up
 *   still <t> <path-trace s> [hour [ev white]]
 *   lamps <t> <x y z> <level>
 * If the route has still lines, it saves one picture per still (still_<t*100>.png) instead of a video.
 *
 * Game time runs in fixed steps of 1/(fps*sub), so the motion is smooth however slow each frame renders,
 * and every saved frame is exactly 1/fps of route time apart. The camera follows a cubic Hermite curve
 * through the keys (the same curve as scripts/routes/route_lib.py and the web pages).
 */
UCLASS(ClassGroup = (Walkthrough), meta = (BlueprintSpawnableComponent))
class WALKTHROUGH_API UWalkRecorderComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UWalkRecorderComponent();

	/** True while a route runs: the pawn ignores the player's input. */
	bool IsRecording() const { return Stage >= 0; }

	/** Model metres (z up, right-handed) to Unreal cm. */
	static FVector FromModel(const FVector& M) { return FVector(M.X * 100.0, -M.Y * 100.0, M.Z * 100.0); }

	/** Hermite position of the route at time T: eye (bLook false) or look-at point, in model metres. */
	FVector Evaluate(double T, bool bLook) const;

	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	struct FKey { double T; FVector Eye; FVector Look; };
	struct FDoorEvent { double T; FVector At; double Radius; bool bOpen; };
	struct FStill { double T; float PathTrace; float Hour; float Ev; float White; };
	struct FLampEvent { double T; FVector At; float Level; };

	bool ParseCommandLine();
	void ApplyEventsUpTo(double T, bool bSnap);
	void Pose(double T);
	void Begin();
	void TickStills();
	void SetPathTracing(bool bOn);
	void Quit();

	TArray<FKey> Keys;
	TArray<FDoorEvent> Doors;
	TArray<FStill> Stills;
	TArray<FLampEvent> LampEvents;
	int32 NextDoor = 0;
	int32 NextLamp = 0;

	FString OutDir;
	int32 Fps = 24;
	float Fov = 84.f;
	float Warm = 20.f;
	int32 Sub = 1;
	float Hour = -1.f;
	int32 Day = -1;
	float Ev = 0.f;
	float White = 6500.f;

	/** -1 idle, 0 waiting for the pawn, 1 warm-up, 2 recording, 3 tail, 4 stills. */
	int32 Stage = -1;
	float Clock = 0.f;
	int32 Frame = 0;
	int32 LastFrame = 0;

	int32 StillIndex = -1;
	int32 StillPhase = 2;     // 0 settling, 1 path tracing, 2 saved / next
	int32 StillTicks = 0;
	double StillStart = 0.0;
	bool bPathTracing = false;

	UPROPERTY()
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY()
	TObjectPtr<AWalkSun> Sun;
};
