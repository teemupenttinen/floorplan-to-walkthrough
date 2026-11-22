#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "WalkCharacter.generated.h"

class UCameraComponent;
class UInputAction;
class UInputMappingContext;
class UWalkRecorderComponent;
class AWalkSun;

/**
 * First-person walker. Enhanced Input actions and key mappings are made in code, so the project needs no
 * input assets (they cannot be authored from scripts anyway).
 *
 * Keys: W A S D / arrows walk, mouse looks, Shift runs, E opens or closes the door you look at,
 * 1-9 jump to the spots of Content/Data/spots.json, F switches the field of view (75 / 90 degrees across),
 * L lamps, T and [ ] change the hour, P cycles quality presets, R path traces the view (R again saves it to
 * Saved/Stills and returns to real time).
 *
 * -WalkQuality=N (0 Fast, 1 Balanced, 2 High, 3 Cinematic) applies a preset for this run only. Judge
 * reflections and shadows on High or Cinematic: a saved Fast preset turns hardware ray tracing off and makes
 * mirrors blocky and shadows jagged.
 */
UCLASS()
class WALKTHROUGH_API AWalkCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AWalkCharacter();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Walk")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Walk")
	TObjectPtr<UWalkRecorderComponent> Recorder;

	UPROPERTY(EditAnywhere, Category = "Walk")
	float WalkSpeed = 140.f;

	UPROPERTY(EditAnywhere, Category = "Walk")
	float RunSpeed = 350.f;

	/** Eye height above the floor (cm). */
	UPROPERTY(EditAnywhere, Category = "Walk")
	float EyeHeight = 160.f;

	UPROPERTY(EditAnywhere, Category = "Walk")
	float UseDistance = 250.f;

	virtual void BeginPlay() override;
	virtual void PawnClientRestart() override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

private:
	UInputAction* MakeAction(const TCHAR* Name, bool bAxis2D);
	void BuildInput();
	void LoadSpots();

	void Move(const FInputActionValue& Value);
	void Look(const FInputActionValue& Value);
	void RunOn();
	void RunOff();
	void Use();
	void CycleFov();
	void ToggleLamps();
	void HourUp();
	void HourDown();
	void CycleQuality();
	void ApplyQuality(int32 Level);
	void TogglePathTracing();
	void GoTo(int32 Index);
	void Say(const FString& Text) const;

	UPROPERTY()
	TObjectPtr<UInputMappingContext> Mapping;

	UPROPERTY()
	TMap<FName, TObjectPtr<UInputAction>> Actions;

	UPROPERTY()
	TObjectPtr<AWalkSun> Sun;

	struct FSpot { FString Name; FVector Loc; float Yaw; };
	TArray<FSpot> Spots;
	int32 FovIndex = 0;
	int32 Quality = 2;
	bool bPathTracing = false;
};
