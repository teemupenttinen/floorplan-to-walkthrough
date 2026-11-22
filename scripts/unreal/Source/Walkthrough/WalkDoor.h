#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WalkDoor.generated.h"

class UStaticMeshComponent;

/**
 * Hinged door. The actor stands on the hinge and the leaf turns about its vertical axis. The leaf mesh is
 * modelled with the hinge at its origin (export_manifest.py moves it there) and exported fully open, so
 * OpenYaw and ClosedYaw are plain Unreal yaws from the manifest.
 * The player's E key and the recorder's "door" route lines set bOpen; Tick turns the leaf toward it.
 */
UCLASS()
class WALKTHROUGH_API AWalkDoor : public AActor
{
	GENERATED_BODY()

public:
	AWalkDoor();

	/** Leaf mesh (collides with the player). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Door")
	TObjectPtr<UStaticMeshComponent> Leaf;

	/** Optional glass of the leaf: turns with it, but the player does not collide with it. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Door")
	TObjectPtr<UStaticMeshComponent> Glass;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door")
	float ClosedYaw = 90.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door")
	float OpenYaw = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door")
	bool bOpen = false;

	/** Degrees per second. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Door")
	float Speed = 150.f;

	UFUNCTION(BlueprintCallable, Category = "Door")
	void Toggle() { bOpen = !bOpen; }

	/** Jump to the target pose at once (route events before the warm-up). */
	UFUNCTION(BlueprintCallable, Category = "Door")
	void Snap();

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void Tick(float DeltaSeconds) override;

private:
	UPROPERTY()
	TObjectPtr<USceneComponent> Hinge;

	float TargetYaw() const { return bOpen ? OpenYaw : ClosedYaw; }
};
